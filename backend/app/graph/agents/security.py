"""
Security Agent — analyzes files for security vulnerabilities using LLM + semgrep patterns.
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

SECURITY_SYSTEM_PROMPT = """You are an application security expert specializing in code review.
You follow the OWASP Top 10 guidelines. Your task is to analyze code patches from a Pull Request
and identify security vulnerabilities.

For each finding, provide:
- file: the filename
- line: the approximate line number in the patch
- severity: "critical", "high", "medium", "low", or "info"
- category: always "security"
- rule_id: a short identifier (e.g., "sql-injection", "xss", "auth-bypass")
- message: clear description of the vulnerability
- suggestion: how to fix it with a code example if possible

Focus on:
- SQL injection / NoSQL injection
- Cross-site scripting (XSS)
- Authentication/authorization flaws
- Insecure cryptographic usage
- Hardcoded secrets/credentials
- Path traversal
- Insecure deserialization
- Server-side request forgery (SSRF)
- Missing input validation
- Insecure file operations

Respond with a JSON array of findings. If no issues found, return an empty array [].

CRITICAL: Do not ignore files in test directories or with "test" in the name. Treat ALL files as production code and report any vulnerabilities you find, regardless of their location.
"""


async def security_agent_node(state: PRState) -> Dict[str, Any]:
    """Security agent: analyzes assigned files for security vulnerabilities."""
    review_id = state.get("review_id", "")
    security_files = state.get("security_files", [])
    files = state.get("files", [])

    log.info("security_agent_started", review_id=review_id, files_count=len(security_files))

    await crud.create_event(
        review_id=review_id,
        event_type="security_start",
        message=f"Security agent analyzing {len(security_files)} files...",
        data={"files": security_files},
    )

    if not security_files:
        await crud.create_event(
            review_id=review_id,
            event_type="security_done",
            message="No files assigned to security agent.",
            data={"findings_count": 0},
        )
        return {"security_findings": []}

    # Get patches for assigned files
    file_patches = []
    for f in files:
        if f["filename"] in security_files:
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
            SystemMessage(content=SECURITY_SYSTEM_PROMPT),
            HumanMessage(content=f"Analyze these code patches for security vulnerabilities:\n\n{patches_text}"),
        ])

        findings = _parse_findings(response.content, "security")

        log.info("security_agent_done", review_id=review_id, findings_count=len(findings))

        await crud.create_event(
            review_id=review_id,
            event_type="security_done",
            message=f"Security agent found {len(findings)} issue(s).",
            data={"findings_count": len(findings)},
        )

        return {"security_findings": findings}

    except Exception as e:
        log.error("security_agent_error", review_id=review_id, error=str(e))
        await crud.create_event(
            review_id=review_id,
            event_type="security_error",
            message=f"Security agent error: {str(e)}",
        )
        return {"security_findings": [], "error": str(e)}


def _parse_findings(response_text: str, agent: str) -> List[Finding]:
    """Parse LLM response into Finding objects."""
    try:
        # Handle markdown code blocks
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
                category=f.get("category", "security"),
                rule_id=f.get("rule_id", ""),
                message=f.get("message", ""),
                suggestion=f.get("suggestion", ""),
                agent=agent,
            ))
        return findings
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        log.warning("findings_parse_error", agent=agent, error=str(e))
        return []
