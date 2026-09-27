"""
Supervisor node: reads PR diff, analyzes files, assigns them to specialist agents.
"""

import json
from typing import Any

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from app.config import settings
from app.db import crud
from app.graph.state import AgentError, PRState
from app.rate_limiter import DailyQuotaExhaustedError, rate_limiter

log = structlog.get_logger()

SUPERVISOR_SYSTEM_PROMPT = """You are a code review supervisor. Given a list of modified files from a Pull Request,
you must assign each file to one or more specialized agents for review:

1. **Security Agent**: All files must be reviewed by the security agent.
2. **Quality Agent**: Files with complex logic, high cyclomatic complexity, missing error handling,
   large classes, poor naming conventions, dead code, or missing tests.
3. **Performance Agent**: Files with database queries inside loops (N+1), unnecessary allocations,
   string concatenation in loops, synchronous I/O in async code, or suboptimal algorithms.

A file CAN be assigned to multiple agents if relevant. In case of uncertainty, assign to all agents.
CRITICAL: All files must pass through the security agent, even if they are already assigned to quality or performance agents. Do NOT exclude any files from security review.
CRITICAL: Do not ignore files in test directories or with "test" in the name. They contain intentional issues for testing purposes and MUST be assigned to the relevant agents as if they were production code.

Respond with a JSON object:
{
  "security_files": ["file1.py", "file2.py"],
  "quality_files": ["file1.py", "file3.py"],
  "performance_files": ["file2.py", "file3.py"],
  "reasoning": "Brief explanation of why each file was assigned."
}
"""


async def supervisor_node(state: PRState) -> dict[str, Any]:
    """
    Supervisor node: reads PR files and assigns them to agents.
    """
    review_id = state.get("review_id", "")
    repo = state.get("repo", "")
    pr_number = state.get("pr_number", 0)

    log.info("supervisor_started", review_id=review_id, repo=repo, pr_number=pr_number)

    await crud.create_event(
        review_id=review_id,
        event_type="supervisor_start",
        message=f"Supervisor analyzing PR #{pr_number} in {repo}...",
        data={"repo": repo, "pr_number": pr_number},
    )

    files = state.get("files", [])

    if not files:
        log.warning("supervisor_no_files", review_id=review_id)
        await crud.create_event(
            review_id=review_id,
            event_type="supervisor_done",
            message="No files found in PR diff.",
            data={"files_count": 0},
        )
        return {
            "security_files": [],
            "quality_files": [],
            "performance_files": [],
            "status": "completed",
        }

    # Build file summary for the LLM
    file_summaries = []
    for f in files:
        summary = f"- {f['filename']} ({f.get('language', 'unknown')}, +{f.get('additions', 0)}/-{f.get('deletions', 0)})"
        if f.get("patch"):
            # Include first 500 chars of the patch for context
            patch_preview = f["patch"][:500]
            summary += f"\n  Patch preview:\n  ```\n  {patch_preview}\n  ```"
        file_summaries.append(summary)

    files_text = "\n".join(file_summaries)

    try:
        await rate_limiter.acquire(estimated_tokens=1000)

        llm = ChatGoogleGenerativeAI(
            model=settings.GEMINI_MODEL,
            google_api_key=settings.GEMINI_API_KEY,
            temperature=0.1,
            max_output_tokens=2048,
        )

        response = await llm.ainvoke(
            [
                SystemMessage(content=SUPERVISOR_SYSTEM_PROMPT),
                HumanMessage(content=f"Here are the modified files in this PR:\n\n{files_text}"),
            ]
        )

        # Parse the JSON response
        response_text = str(response.text)
        # Try to extract JSON from the response
        try:
            # Handle markdown code blocks
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            assignments = json.loads(response_text)
        except (json.JSONDecodeError, IndexError):
            # Fallback: assign all files to all agents
            log.warning("supervisor_parse_error", response=response_text[:200])
            all_filenames = [f["filename"] for f in files]
            assignments = {
                "security_files": all_filenames,
                "quality_files": all_filenames,
                "performance_files": all_filenames,
            }

        # Keep only real file names: the model may invent or mangle paths
        known = [f["filename"] for f in files]

        def _valid(key: str) -> list[str]:
            chosen = set(assignments.get(key) or [])
            return [name for name in known if name in chosen]

        # Security review is not left to the model's judgment: every file gets it
        security_files = known
        quality_files = _valid("quality_files")
        performance_files = _valid("performance_files")

        log.info(
            "supervisor_assignments",
            review_id=review_id,
            security=len(security_files),
            quality=len(quality_files),
            performance=len(performance_files),
        )

        await crud.create_event(
            review_id=review_id,
            event_type="supervisor_done",
            message=f"Assigned {len(files)} files to agents: {len(security_files)} security, {len(quality_files)} quality, {len(performance_files)} performance",
            data={
                "files_count": len(files),
                "security_files": security_files,
                "quality_files": quality_files,
                "performance_files": performance_files,
                "reasoning": assignments.get("reasoning", ""),
            },
        )

        return {
            "security_files": security_files,
            "quality_files": quality_files,
            "performance_files": performance_files,
            "status": "running",
        }

    except DailyQuotaExhaustedError:
        raise
    except Exception as e:
        log.error("supervisor_error", review_id=review_id, error=str(e))
        await crud.create_event(
            review_id=review_id,
            event_type="supervisor_error",
            message=f"Supervisor failed ({type(e).__name__}): every file goes to every agent.",
        )
        # Fallback: assign all files to all agents
        all_filenames = [f["filename"] for f in files]
        return {
            "security_files": all_filenames,
            "quality_files": all_filenames,
            "performance_files": all_filenames,
            "status": "running",
            "errors": [AgentError(agent="supervisor", message=f"{type(e).__name__}: {e!s}"[:500])],
        }
