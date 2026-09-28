"""Shared machinery of the review agents.

Every agent follows the same steps:
1. render its files as numbered diffs (see app.diff.parser)
2. split them into batches that fit the token budget of one LLM call
3. review the batches concurrently with structured output
4. validate the answers: unknown files are dropped, lines are mapped onto the diff
"""

import asyncio
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import settings
from app.db import crud
from app.diff.parser import (
    Hunk,
    ParsedPatch,
    find_evidence_line,
    parse_patch,
    render_hunk,
    resolve_line,
)
from app.graph.prompts import get_prompt
from app.graph.schemas import AgentReview, ReviewFinding
from app.graph.state import AgentError, Finding, PRFile, PRState
from app.llm import factory
from app.llm.invoke import estimate_tokens, invoke_structured
from app.rate_limiter import DailyQuotaExhaustedError

log = structlog.get_logger()

AgentName = Literal["security", "quality", "performance"]

MAX_OUTPUT_TOKENS = 4096


@dataclass(frozen=True)
class AgentSpec:
    name: AgentName
    title: str
    focus: str  # what to look for, used in the user message


def agent_system_prompt(agent: AgentName) -> str:
    """The agent's own prompt followed by the rules shared by every agent."""
    return get_prompt(agent).text + "\n\n" + get_prompt("agent_rules").text


@dataclass(frozen=True)
class DiffChunk:
    """A file, or a slice of its hunks, rendered with line numbers."""

    filename: str
    language: str
    text: str
    tokens: int
    part: int = 1
    parts: int = 1


def _truncate_hunk(hunk: Hunk, budget_tokens: int) -> str:
    text = render_hunk(hunk)
    max_chars = budget_tokens * 3
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n[... hunk truncated: too large for a single review call ...]"


def build_chunks(file: PRFile, budget_tokens: int) -> list[DiffChunk]:
    """Render a file as one chunk, or as several when its diff exceeds the budget."""
    parsed = parse_patch(file.get("patch", ""))
    rendered_hunks = [_truncate_hunk(hunk, budget_tokens) for hunk in parsed.hunks]
    if not rendered_hunks:
        return []

    groups: list[list[str]] = [[]]
    group_tokens = 0
    for text in rendered_hunks:
        tokens = estimate_tokens(text)
        if groups[-1] and group_tokens + tokens > budget_tokens:
            groups.append([])
            group_tokens = 0
        groups[-1].append(text)
        group_tokens += tokens

    language = file.get("language", "unknown")
    return [
        DiffChunk(
            filename=file["filename"],
            language=language,
            text="\n".join(group),
            tokens=estimate_tokens("\n".join(group)),
            part=index,
            parts=len(groups),
        )
        for index, group in enumerate(groups, start=1)
    ]


def build_batches(chunks: Sequence[DiffChunk], budget_tokens: int) -> list[list[DiffChunk]]:
    """Pack chunks into batches whose estimated size stays within the budget."""
    batches: list[list[DiffChunk]] = []
    current: list[DiffChunk] = []
    current_tokens = 0
    for chunk in chunks:
        if current and current_tokens + chunk.tokens > budget_tokens:
            batches.append(current)
            current, current_tokens = [], 0
        current.append(chunk)
        current_tokens += chunk.tokens
    if current:
        batches.append(current)
    return batches


def render_batch(batch: Sequence[DiffChunk], spec: AgentSpec, pr_title: str) -> str:
    sections = []
    for chunk in batch:
        part = f", part {chunk.part} of {chunk.parts}" if chunk.parts > 1 else ""
        sections.append(f"### File: {chunk.filename} ({chunk.language}{part})\n{chunk.text}")
    body = "\n\n".join(sections)
    return (
        f"Review these pull request changes for {spec.focus}.\n\n"
        f"<pr_diff>\nPull request title: {pr_title}\n\n{body}\n</pr_diff>"
    )


def _normalize_path(path: str) -> str:
    path = path.strip().strip("`").strip()
    for prefix in ("./", "a/", "b/"):
        if path.startswith(prefix):
            path = path[len(prefix) :]
    return path


def normalize_rule_id(rule_id: str) -> str:
    """Kebab-case rule ids, so that SQL_INJECTION, SQLInjection and sql-injection match."""
    text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1-\2", rule_id.strip())
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", text)
    text = re.sub(r"[^a-zA-Z0-9+]+", "-", text).strip("-")
    return text.lower()


@dataclass
class ValidationStats:
    kept: int = 0
    dropped_unknown_file: int = 0
    corrected_by_evidence: int = 0  # reported line differed from the quoted code
    moved_to_nearest_line: int = 0
    not_on_diff: int = 0


def validate_findings(
    findings: Sequence[ReviewFinding],
    parsed_by_file: dict[str, ParsedPatch],
    agent: AgentName,
    stats: ValidationStats,
) -> list[Finding]:
    """Drop findings on files outside the batch and map lines onto the diff.

    Findings whose line cannot be placed on the diff keep line 0: they are
    published in the review summary instead of as inline comments.
    """
    valid: list[Finding] = []
    for item in findings:
        filename = _normalize_path(item.file)
        parsed = parsed_by_file.get(filename)
        if parsed is None:
            stats.dropped_unknown_file += 1
            continue
        # The quoted code is more reliable than the reported line number
        line: int | None = find_evidence_line(parsed, item.evidence, near=item.line)
        if line is not None:
            if line != item.line:
                stats.corrected_by_evidence += 1
        else:
            line, resolution = resolve_line(parsed, item.line)
            if resolution == "nearest":
                stats.moved_to_nearest_line += 1
            elif resolution == "none":
                stats.not_on_diff += 1
        valid.append(
            Finding(
                file=filename,
                line=line or 0,
                severity=item.severity,
                category=agent,
                rule_id=normalize_rule_id(item.rule_id) or f"{agent}-issue",
                message=item.message.strip(),
                suggestion=item.suggestion.strip(),
                agent=agent,
                confidence=round(item.confidence, 2),
                cwe=item.cwe if agent == "security" else None,
                evidence=item.evidence.strip()[:1000],
            )
        )
        stats.kept += 1
    return valid


async def run_review_agent(state: PRState, spec: AgentSpec) -> dict[str, Any]:
    """Run one specialist agent over the files assigned to it."""
    review_id = state.get("review_id", "")
    assigned_files: list[str] = state.get(f"{spec.name}_files", [])  # type: ignore[assignment]
    assigned = set(assigned_files)
    files = [f for f in state.get("files", []) if f["filename"] in assigned]
    findings_key = f"{spec.name}_findings"

    await crud.create_event(
        review_id=review_id,
        event_type=f"{spec.name}_start",
        message=f"{spec.title} agent analyzing {len(files)} files...",
        data={"files": [f["filename"] for f in files]},
    )
    if not files:
        await crud.create_event(
            review_id=review_id,
            event_type=f"{spec.name}_done",
            message=f"No files assigned to the {spec.name} agent.",
            data={"findings_count": 0},
        )
        return {findings_key: []}

    budget = factory.input_token_budget(MAX_OUTPUT_TOKENS)
    chunks = [chunk for file in files for chunk in build_chunks(file, budget)]
    batches = build_batches(chunks, budget)
    parsed_by_file = {f["filename"]: parse_patch(f.get("patch", "")) for f in files}
    pr_title = str(state.get("pr_metadata", {}).get("title", ""))
    semaphore = asyncio.Semaphore(max(settings.LLM_MAX_CONCURRENCY, 1))
    system = SystemMessage(content=agent_system_prompt(spec.name))

    async def review(batch: list[DiffChunk]) -> AgentReview:
        async with semaphore:
            return await invoke_structured(
                [system, HumanMessage(content=render_batch(batch, spec, pr_title))],
                AgentReview,
                temperature=0.1,
                max_output_tokens=MAX_OUTPUT_TOKENS,
                purpose=f"{spec.name}_agent",
            )

    results = await asyncio.gather(*(review(b) for b in batches), return_exceptions=True)

    if any(isinstance(r, DailyQuotaExhaustedError) for r in results):
        # Not an agent failure: the whole review must stop and be retried later
        raise next(r for r in results if isinstance(r, DailyQuotaExhaustedError))

    stats = ValidationStats()
    findings: list[Finding] = []
    failures: list[BaseException] = []
    for result in results:
        if isinstance(result, BaseException):
            failures.append(result)
            continue
        findings.extend(validate_findings(result.findings, parsed_by_file, spec.name, stats))

    errors: list[AgentError] = []
    if failures:
        first = failures[0]
        log.error(
            f"{spec.name}_agent_error",
            review_id=review_id,
            failed_batches=len(failures),
            batches=len(batches),
            error_type=type(first).__name__,
            error=str(first)[:300],
        )
        errors.append(
            AgentError(
                agent=spec.name,
                message=f"{len(failures)} of {len(batches)} batches failed "
                f"({type(first).__name__}: {str(first)[:300]})",
            )
        )
        await crud.create_event(
            review_id=review_id,
            event_type=f"{spec.name}_error",
            message=f"{spec.title} agent: {len(failures)} of {len(batches)} batch(es) failed "
            f"({type(first).__name__}).",
        )
        if len(failures) == len(batches):
            return {findings_key: [], "errors": errors}

    log.info(
        f"{spec.name}_agent_done",
        review_id=review_id,
        batches=len(batches),
        findings=stats.kept,
        dropped_unknown_file=stats.dropped_unknown_file,
        corrected_by_evidence=stats.corrected_by_evidence,
        moved_to_nearest_line=stats.moved_to_nearest_line,
        not_on_diff=stats.not_on_diff,
    )
    await crud.create_event(
        review_id=review_id,
        event_type=f"{spec.name}_done",
        message=f"{spec.title} agent found {stats.kept} issue(s) in {len(batches)} call(s).",
        data={
            "findings_count": stats.kept,
            "batches": len(batches),
            "dropped_unknown_file": stats.dropped_unknown_file,
            "corrected_by_evidence": stats.corrected_by_evidence,
            "moved_to_nearest_line": stats.moved_to_nearest_line,
            "not_on_diff": stats.not_on_diff,
        },
    )
    output: dict[str, Any] = {findings_key: findings}
    if errors:
        output["errors"] = errors
    return output
