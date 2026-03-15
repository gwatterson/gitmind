"""
Performance Agent — detects performance anti-patterns: N+1 queries, loop I/O, allocations.
"""

import json
import structlog
from typing import Dict, List, Any

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from app.config import settings
from app.rate_limiter import rate_limiter
from app.graph.state import PRState, Finding
from app.db import crud

log = structlog.get_logger()

PERFORMANCE_SYSTEM_PROMPT = """You are a performance engineering expert specializing in code review.
Your task is to analyze code patches from a Pull Request and identify performance issues.

For each finding, provide:
- file: the filename
- line: the approximate line number in the patch
- severity: "critical", "high", "medium", "low", or "info"
- category: always "performance"
- rule_id: a short identifier (e.g., "n-plus-1", "loop-io", "string-concat-loop")
- message: clear description of the performance issue
- suggestion: how to optimize with a code example if possible

Focus on:
- N+1 query patterns (database queries inside loops)
- I/O operations inside loops (file reads, HTTP requests)
- String concatenation in loops (use StringBuilder/join instead)
- Unnecessary object allocations in hot paths
- Missing database indexes (queries without WHERE on indexed columns)
- Synchronous blocking calls in async code
- Unbounded data fetching (SELECT * without LIMIT)
- Inefficient algorithms (O(n²) when O(n log n) or O(n) is possible)
- Memory leaks (unclosed resources, accumulating data structures)
- Redundant computations that could be cached/memoized

Respond with a JSON array of findings. If no issues found, return an empty array [].

CRITICAL: Do not ignore files in test directories or with "test" in the name. Treat ALL files as production code and report any performance issues you find.
"""


async def performance_agent_node(state: PRState) -> Dict[str, Any]:
    """Performance agent: analyzes assigned files for performance anti-patterns."""
    review_id = state.get("review_id", "")
    performance_files = state.get("performance_files", [])
    files = state.get("files", [])

    log.info("performance_agent_started", review_id=review_id, files_count=len(performance_files))

    await crud.create_event(
        review_id=review_id,
        event_type="performance_start",
        message=f"Performance agent analyzing {len(performance_files)} files...",
        data={"files": performance_files},
    )

    if not performance_files:
        await crud.create_event(
            review_id=review_id,
            event_type="performance_done",
            message="No files assigned to performance agent.",
            data={"findings_count": 0},
        )
        return {"performance_findings": []}

    # Get patches for assigned files
    file_patches = []
    for f in files:
        if f["filename"] in performance_files:
            file_patches.append(
                f"### {f['filename']} ({f.get('language', 'unknown')})\n"
                f"```\n{f.get('patch', 'No patch available')}\n```"
            )

    patches_text = "\n\n".join(file_patches)

    try:
        await rate_limiter.acquire(estimated_tokens=2000)

        llm = ChatGoogleGenerativeAI(
            model=settings.GEMINI_MODEL,
            google_api_key=settings.GEMINI_API_KEY,
            temperature=0.1,
            max_output_tokens=4096,
        )

        response = await llm.ainvoke([
            SystemMessage(content=PERFORMANCE_SYSTEM_PROMPT),
            HumanMessage(content=f"Analyze these code patches for performance issues:\n\n{patches_text}"),
        ])

        findings = _parse_findings(response.content, "performance")

        log.info("performance_agent_done", review_id=review_id, findings_count=len(findings))

        await crud.create_event(
            review_id=review_id,
            event_type="performance_done",
            message=f"Performance agent found {len(findings)} issue(s).",
            data={"findings_count": len(findings)},
        )

        return {"performance_findings": findings}

    except Exception as e:
        log.error("performance_agent_error", review_id=review_id, error=str(e))
        await crud.create_event(
            review_id=review_id,
            event_type="performance_error",
            message=f"Performance agent error: {str(e)}",
        )
        return {"performance_findings": [], "error": str(e)}


def _parse_findings(response_text: str, agent: str) -> List[Finding]:
    """Parse LLM response into Finding objects."""
    try:
        text = response_text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        raw_findings = json.loads(text)
        if not isinstance(raw_findings, list):
            raw_findings = [raw_findings]

        findings = []
        for f in raw_findings:
            findings.append(Finding(
                file=f.get("file", "unknown"),
                line=int(f.get("line", 0)),
                severity=f.get("severity", "info"),
                category=f.get("category", "performance"),
                rule_id=f.get("rule_id", ""),
                message=f.get("message", ""),
                suggestion=f.get("suggestion", ""),
                agent=agent,
            ))
        return findings
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        log.warning("findings_parse_error", agent=agent, error=str(e))
        return []
