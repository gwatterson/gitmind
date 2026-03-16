"""
Quality Agent — analyzes code quality: complexity, naming, structure, maintainability.
"""

import json
import structlog
from typing import Dict, List, Any
from pydantic import BaseModel, Field

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from app.config import settings
from app.rate_limiter import rate_limiter
from app.graph.state import PRState, Finding
from app.db import crud

log = structlog.get_logger()

class FindingModel(BaseModel):
    file: str = Field(description="the filename")
    line: int = Field(default=0, description="the approximate line number in the patch")
    severity: str = Field(description='"critical", "high", "medium", "low", or "info"')
    category: str = Field(description='always "quality"')
    rule_id: str = Field(description='a short identifier (e.g., "high-complexity", "missing-error-handling", "naming-convention")')
    message: str = Field(description='clear description of the issue')
    suggestion: str = Field(default="", description='how to improve with a code example if possible')

class QualityReview(BaseModel):
    findings: List[FindingModel] = Field(default_factory=list, description="List of quality findings")

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

Analyze the code and extract the findings using the provided structured output format.

CRITICAL: Do not ignore files in test directories or with "test" in the name. Treat ALL files as production code and report any structural or quality issues you find, regardless of their location.
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

        structured_llm = llm.with_structured_output(QualityReview)

        response = await structured_llm.ainvoke([
            SystemMessage(content=QUALITY_SYSTEM_PROMPT),
            HumanMessage(content=f"Analyze these code patches for quality issues:\n\n{patches_text}"),
        ])

        findings = []
        if response and response.findings:
            for f in response.findings:
                findings.append(Finding(
                    file=f.file,
                    line=f.line,
                    severity=f.severity,
                    category="quality",
                    rule_id=f.rule_id,
                    message=f.message,
                    suggestion=f.suggestion,
                    agent="quality",
                ))

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
