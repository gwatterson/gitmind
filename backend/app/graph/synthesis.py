"""
Synthesis node: aggregates findings from all agents, deduplicates, determines verdict.
"""

import json
from typing import Any

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from app.config import settings
from app.db import crud
from app.graph.state import Finding, PRState
from app.rate_limiter import rate_limiter

log = structlog.get_logger()

REVIEW_AGENTS = ("security", "quality", "performance")

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

SYNTHESIS_SYSTEM_PROMPT = """You are a senior engineering lead summarizing a code review.
Given a list of findings from security, quality, and performance analyses,
write a concise, professional PR review summary (max 300 words).

Structure your summary:
1. Overall Assessment: One sentence verdict
2. Critical Issues (if any): Must be addressed before merge
3. Key Findings: Top 3-5 most important issues by category
4. Recommendations: Brief actionable next steps

Be direct, professional, and constructive. Avoid unnecessary filler.
Answer in plain text, not markdown.
"""


def deduplicate_findings(findings: list[Finding]) -> list[Finding]:
    """Remove duplicate findings (same file + line + rule_id)."""
    seen = set()
    unique = []
    for f in findings:
        key = (f.get("file", ""), f.get("line", 0), f.get("rule_id", ""))
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique


def sort_findings(findings: list[Finding]) -> list[Finding]:
    """Sort findings by severity (critical first)."""
    return sorted(findings, key=lambda f: SEVERITY_ORDER.get(f.get("severity", "info"), 99))


def determine_verdict(findings: list[Finding]) -> str:
    """Determine review verdict based on findings severity."""
    severities = {f.get("severity", "info") for f in findings}

    if "critical" in severities:
        return "request_changes"
    elif "high" in severities:
        return "request_changes"
    elif severities - {"low", "info"}:  # has medium or above
        return "comment"
    else:
        return "approve"


async def synthesis_node(state: PRState) -> dict[str, Any]:
    """
    Synthesis node: aggregates, deduplicates, sorts findings and generates summary.
    """
    review_id = state.get("review_id", "")

    log.info("synthesis_started", review_id=review_id)

    await crud.create_event(
        review_id=review_id,
        event_type="synthesis_start",
        message="Aggregating findings from all agents...",
    )

    # Agents that were given files but failed: their silence is not a clean result
    failed_agents = sorted(
        {error["agent"] for error in state.get("errors", []) if error["agent"] in REVIEW_AGENTS}
    )
    agents_that_ran = {agent for agent in REVIEW_AGENTS if state.get(f"{agent}_files")}

    if agents_that_ran and agents_that_ran.issubset(failed_agents):
        message = "All review agents failed: " + ", ".join(failed_agents) + "."
        log.error("synthesis_all_agents_failed", review_id=review_id, agents=failed_agents)
        await crud.update_review(
            review_id, status="failed", error=message, completed_at=crud.utc_now()
        )
        await crud.create_event(review_id=review_id, event_type="synthesis_failed", message=message)
        return {"all_findings": [], "review_summary": "", "verdict": "", "status": "failed"}

    # Collect findings from all agents
    security_findings = state.get("security_findings", [])
    quality_findings = state.get("quality_findings", [])
    performance_findings = state.get("performance_findings", [])

    all_findings = security_findings + quality_findings + performance_findings

    # Deduplicate and sort
    all_findings = deduplicate_findings(all_findings)
    all_findings = sort_findings(all_findings)

    # Determine verdict. A partial review can never approve the PR.
    verdict = determine_verdict(all_findings)
    if failed_agents and verdict == "approve":
        verdict = "comment"

    # Store findings in DB
    if all_findings:
        await crud.create_findings_batch(review_id, all_findings)

    log.info(
        "synthesis_findings",
        review_id=review_id,
        total=len(all_findings),
        security=len(security_findings),
        quality=len(quality_findings),
        performance=len(performance_findings),
        failed_agents=failed_agents,
        verdict=verdict,
    )

    # Generate summary via LLM
    review_summary = ""
    if all_findings:
        try:
            await rate_limiter.acquire(estimated_tokens=1500)

            llm = ChatGoogleGenerativeAI(
                model=settings.GEMINI_MODEL,
                google_api_key=settings.GEMINI_API_KEY,
                temperature=0.2,
                max_output_tokens=3072,
            )

            findings_text = json.dumps(all_findings, indent=2, default=str)

            response = await llm.ainvoke(
                [
                    SystemMessage(content=SYNTHESIS_SYSTEM_PROMPT),
                    HumanMessage(
                        content=f"PR: {state.get('repo', '')} #{state.get('pr_number', '')}\n"
                        f"Verdict: {verdict}\n\n"
                        f"Findings ({len(all_findings)} total):\n{findings_text}"
                    ),
                ]
            )
            review_summary = str(response.text)
        except Exception as e:
            # Quota exhaustion included: the findings are already stored, so the
            # review completes with a deterministic summary instead of failing.
            log.error("synthesis_summary_error", error=str(e))
            review_summary = _generate_fallback_summary(all_findings, verdict)
    elif failed_agents:
        review_summary = "No issues were found by the agents that completed."
    else:
        review_summary = "No issues found. This PR looks clean."

    if failed_agents:
        review_summary += (
            "\n\nNote: this review is incomplete because the following agents failed: "
            + ", ".join(failed_agents)
            + "."
        )

    status = "hitl_pending" if settings.HITL_ENABLED else "completed"
    await crud.update_review(
        review_id,
        status=status,
        verdict=verdict,
        summary=review_summary,
        error=("Agents failed: " + ", ".join(failed_agents)) if failed_agents else None,
        completed_at=None if settings.HITL_ENABLED else crud.utc_now(),
    )

    await crud.create_event(
        review_id=review_id,
        event_type="synthesis_done",
        message=f"Review complete. Verdict: {verdict}. {len(all_findings)} findings.",
        data={
            "verdict": verdict,
            "total_findings": len(all_findings),
            "failed_agents": failed_agents,
            "summary": review_summary,
            "summary_preview": review_summary[:200],
        },
    )

    return {
        "all_findings": all_findings,
        "review_summary": review_summary,
        "verdict": verdict,
        "status": status,
    }


def _generate_fallback_summary(findings: list[Finding], verdict: str) -> str:
    """Generate a simple summary without calling the LLM."""
    severity_counts: dict[str, int] = {}
    for f in findings:
        sev = f.get("severity", "info")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    lines = [f"## Code Review Summary\n\n**Verdict: {verdict.upper()}**\n"]
    lines.append(f"Found **{len(findings)}** total issues:\n")
    for sev in ["critical", "high", "medium", "low", "info"]:
        count = severity_counts.get(sev, 0)
        if count:
            lines.append(f"- {sev.capitalize()}: {count}")

    return "\n".join(lines)
