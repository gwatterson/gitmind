"""
Quality Agent — analyzes code quality: complexity, naming, structure, maintainability.
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

QUALITY_SYSTEM_PROMPT = """You are a senior software engineer specializing in code quality review.
Your task is to analyze code patches from a Pull Request and identify quality issues.

For each finding, provide:
- file: the filename
- line: the approximate line number in the patch
- severity: "critical", "high", "medium", "low", or "info"
- category: always "quality"
- rule_id: a short identifier (e.g., "high-complexity", "missing-error-handling", "naming-convention")
- message: clear description of the issue
- suggestion: how to improve with a code example if possible

Focus on:
- Functions with high cyclomatic complexity (>10)
- Classes exceeding 300 lines
- Missing error handling / bare except clauses
- Poor naming conventions
- Dead code / unused imports
- Missing type hints
- Duplicated code patterns
- Deeply nested conditionals (>3 levels)
- Missing docstrings on public APIs
- Code that violates SOLID principles

Respond with a JSON array of findings. If no issues found, return an empty array [].

CRITICAL: Do not ignore files in test directories or with "test" in the name. Treat ALL files as production code and report any structural or quality issues you find.
"""


async def quality_agent_node(state: PRState) -> Dict[str, Any]:
    """Quality agent: analyzes assigned files for code quality issues."""
    review_id = state.get("review_id", "")
    quality_files = state.get("quality_files", [])
    files = state.get("files", [])

    log.info("quality_agent_started", review_id=review_id, files_count=len(quality_files))

    await crud.create_event(
        review_id=review_id,
        event_type="quality_start",
        message=f"Quality agent analyzing {len(quality_files)} files...",
        data={"files": quality_files},
    )

    if not quality_files:
        await crud.create_event(
            review_id=review_id,
            event_type="quality_done",
            message="No files assigned to quality agent.",
            data={"findings_count": 0},
        )
        return {"quality_findings": []}

    # Get patches for assigned files
    file_patches = []
    for f in files:
        if f["filename"] in quality_files:
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
            SystemMessage(content=QUALITY_SYSTEM_PROMPT),
            HumanMessage(content=f"Analyze these code patches for quality issues:\n\n{patches_text}"),
        ])

        findings = _parse_findings(response.content, "quality")

        log.info("quality_agent_done", review_id=review_id, findings_count=len(findings))

        await crud.create_event(
            review_id=review_id,
            event_type="quality_done",
            message=f"Quality agent found {len(findings)} issue(s).",
            data={"findings_count": len(findings)},
        )

        return {"quality_findings": findings}

    except Exception as e:
        log.error("quality_agent_error", review_id=review_id, error=str(e))
        await crud.create_event(
            review_id=review_id,
            event_type="quality_error",
            message=f"Quality agent error: {str(e)}",
        )
        return {"quality_findings": [], "error": str(e)}


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
                category=f.get("category", "quality"),
                rule_id=f.get("rule_id", ""),
                message=f.get("message", ""),
                suggestion=f.get("suggestion", ""),
                agent=agent,
            ))
        return findings
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        log.warning("findings_parse_error", agent=agent, error=str(e))
        return []
