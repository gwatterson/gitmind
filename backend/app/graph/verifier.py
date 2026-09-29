"""
Verifier node: a second opinion on every finding before synthesis (PLAN.md F8.5).

The evaluation showed that the agents find most real problems but report many false
alarms, and that the confidence they report does not tell the two apart. The verifier
re-reads each file's diff together with the findings on it and judges, finding by
finding, whether the code supports the claim. Findings below VERIFIER_MIN_CONFIDENCE
are suppressed: kept in the database for analysis, never published.

One call per file keeps the cost low. The verifier fails open: if a call fails or a
finding gets no answer, the finding is kept as the agent reported it.
"""

import asyncio
import json
from contextlib import AbstractContextManager
from typing import Any

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import settings
from app.db import crud
from app.diff.parser import parse_patch, render_numbered
from app.graph.prompts import get_prompt
from app.graph.schemas import VerifierReview
from app.graph.state import AgentError, Finding, PRFile, PRState
from app.llm import factory
from app.llm.invoke import invoke_structured
from app.rate_limiter import DailyQuotaExhaustedError

log = structlog.get_logger()

AGENT_KEYS = ("security_findings", "quality_findings", "performance_findings")
MAX_OUTPUT_TOKENS = 2048


def _provider() -> AbstractContextManager[None]:
    return factory.use_provider(settings.VERIFIER_PROVIDER or None)


def _render_request(file: PRFile, findings: list[Finding], pr_title: str) -> str:
    with _provider():
        budget_chars = factory.input_token_budget(MAX_OUTPUT_TOKENS) * 3
    diff = render_numbered(parse_patch(file.get("patch", "")))
    if len(diff) > budget_chars:
        diff = diff[:budget_chars] + "\n[... diff truncated ...]"
    listed = [
        {
            "id": index,
            "line": f.get("line"),
            "category": f.get("category"),
            "severity": f.get("severity"),
            "message": f.get("message"),
            "evidence": f.get("evidence", ""),
        }
        for index, f in enumerate(findings)
    ]
    return (
        f"Findings to verify on {file['filename']}:\n{json.dumps(listed, indent=1)}\n\n"
        f"<pr_diff>\nPull request title: {pr_title}\n\n"
        f"### File: {file['filename']} ({file.get('language', 'unknown')})\n{diff}\n</pr_diff>"
    )


async def verify_node(state: PRState) -> dict[str, Any]:
    """Keep the findings the verifier confirms, suppress the others."""
    if not settings.VERIFIER_ENABLED:
        return {}
    review_id = state.get("review_id", "")
    agent_findings: dict[str, list[Finding]] = {
        "security_findings": state.get("security_findings", []),
        "quality_findings": state.get("quality_findings", []),
        "performance_findings": state.get("performance_findings", []),
    }
    tagged = [(key, f) for key in AGENT_KEYS for f in agent_findings[key]]
    if not tagged:
        return {}

    files = {f["filename"]: f for f in state.get("files", [])}
    by_file: dict[str, list[int]] = {}
    for index, (_, finding) in enumerate(tagged):
        by_file.setdefault(finding["file"], []).append(index)

    await crud.create_event(
        review_id=review_id,
        event_type="verify_start",
        message=f"Verifier checking {len(tagged)} finding(s) in {len(by_file)} file(s)...",
    )
    pr_title = str(state.get("pr_metadata", {}).get("title", ""))
    system = SystemMessage(content=get_prompt("verifier").text)
    semaphore = asyncio.Semaphore(max(settings.LLM_MAX_CONCURRENCY, 1))

    async def check(filename: str, indexes: list[int]) -> VerifierReview:
        findings = [tagged[i][1] for i in indexes]
        file = files.get(filename) or PRFile(
            filename=filename, language="unknown", patch="", additions=0, deletions=0
        )
        async with semaphore:
            with _provider():
                return await invoke_structured(
                    [system, HumanMessage(content=_render_request(file, findings, pr_title))],
                    VerifierReview,
                    temperature=0.0,
                    max_output_tokens=MAX_OUTPUT_TOKENS,
                    purpose="verifier",
                )

    names = list(by_file)
    results = await asyncio.gather(*(check(n, by_file[n]) for n in names), return_exceptions=True)
    if any(isinstance(r, DailyQuotaExhaustedError) for r in results):
        raise next(r for r in results if isinstance(r, DailyQuotaExhaustedError))

    threshold = settings.VERIFIER_MIN_CONFIDENCE
    kept: dict[str, list[Finding]] = {key: [] for key in AGENT_KEYS}
    suppressed: list[Finding] = []
    failures = 0
    for name, result in zip(names, results, strict=True):
        indexes = by_file[name]
        answers = {}
        if isinstance(result, BaseException):
            failures += 1
            log.error("verifier_error", review_id=review_id, file=name, error=str(result)[:300])
        else:
            answers = {v.id: v for v in result.verdicts}
        for position, index in enumerate(indexes):
            key, finding = tagged[index]
            answer = answers.get(position)
            if answer is None:  # fail open: keep the agent's finding unchanged
                kept[key].append(finding)
                continue
            checked = Finding(
                **{
                    **finding,
                    "confidence": round(answer.confidence, 2),
                    "verifier_confidence": round(answer.confidence, 2),
                    "verifier_real": answer.real,
                    "verifier_note": answer.reason.strip()[:500],
                }
            )
            if answer.real and answer.confidence >= threshold:
                kept[key].append(checked)
            else:
                suppressed.append(checked)

    kept_count = sum(len(v) for v in kept.values())
    log.info(
        "verifier_done",
        review_id=review_id,
        checked=len(tagged),
        kept=kept_count,
        suppressed=len(suppressed),
        failed_files=failures,
    )
    await crud.create_event(
        review_id=review_id,
        event_type="verify_done",
        message=f"Verifier kept {kept_count} of {len(tagged)} finding(s)"
        + (f", {failures} file(s) could not be checked." if failures else "."),
        data={"kept": kept_count, "suppressed": len(suppressed), "failed_files": failures},
    )
    output: dict[str, Any] = {**kept, "suppressed_findings": suppressed}
    if failures:
        output["errors"] = [
            AgentError(agent="verifier", message=f"{failures} file(s) could not be verified")
        ]
    return output
