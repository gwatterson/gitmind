"""
Supervisor node: decides the review scope and assigns files to the specialist agents.

1. Deterministic scope: generated, vendored and binary files are skipped, and very large
   pull requests are cut at MAX_REVIEW_FILES / MAX_REVIEW_PATCH_CHARS (the summary says so).
2. Every reviewable file goes to the security agent: that is not left to the model.
3. Quality and performance assignment: small pull requests go to every agent without an
   LLM call; larger ones are triaged by the model with structured output.
"""

from typing import Any

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import settings
from app.db import crud
from app.diff.files import exclusion_reason
from app.graph.prompts import get_prompt
from app.graph.schemas import SupervisorAssignment
from app.graph.state import AgentError, PRFile, PRState, SkippedFile
from app.llm.invoke import invoke_structured
from app.rate_limiter import DailyQuotaExhaustedError

log = structlog.get_logger()

# Up to this many files, triage is not worth an LLM call: every agent reviews every file
SMALL_PR_FILES = 3

PATCH_PREVIEW_CHARS = 600


def select_scope(files: list[PRFile]) -> tuple[list[PRFile], list[SkippedFile]]:
    """Split the changed files into reviewable ones and skipped ones (with the reason)."""
    reviewable: list[PRFile] = []
    skipped: list[SkippedFile] = []
    total_chars = 0
    for file in files:
        patch = file.get("patch", "")
        reason = exclusion_reason(file["filename"], patch, settings.review_exclude_patterns)
        if reason is None and len(reviewable) >= settings.MAX_REVIEW_FILES:
            reason = f"review limit of {settings.MAX_REVIEW_FILES} files reached"
        if reason is None and total_chars + len(patch) > settings.MAX_REVIEW_PATCH_CHARS:
            reason = "review size limit reached"
        if reason is None:
            reviewable.append(file)
            total_chars += len(patch)
        else:
            skipped.append(SkippedFile(filename=file["filename"], reason=reason))
    return reviewable, skipped


def _describe(files: list[PRFile]) -> str:
    lines = []
    for f in files:
        header = (
            f"- {f['filename']} ({f.get('language', 'unknown')}, "
            f"+{f.get('additions', 0)}/-{f.get('deletions', 0)})"
        )
        preview = f.get("patch", "")[:PATCH_PREVIEW_CHARS]
        lines.append(f"{header}\n{preview}")
    return "<pr_diff>\n" + "\n\n".join(lines) + "\n</pr_diff>"


async def supervisor_node(state: PRState) -> dict[str, Any]:
    """Decide the review scope and assign files to agents."""
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

    files, skipped = select_scope(state.get("files", []))
    names = [f["filename"] for f in files]
    result: dict[str, Any] = {
        "skipped_files": skipped,
        "security_files": names,
        "quality_files": names,
        "performance_files": names,
        "status": "running",
    }
    reasoning = ""

    if len(files) > SMALL_PR_FILES:
        try:
            assignment = await invoke_structured(
                [
                    SystemMessage(content=get_prompt("supervisor").text),
                    HumanMessage(content=f"Changed files:\n\n{_describe(files)}"),
                ],
                SupervisorAssignment,
                temperature=0.0,
                max_output_tokens=1024,
                purpose="supervisor",
            )
            chosen_quality = set(assignment.quality_files)
            chosen_performance = set(assignment.performance_files)
            # Keep only real file names: the model may invent or mangle paths
            result["quality_files"] = [n for n in names if n in chosen_quality]
            result["performance_files"] = [n for n in names if n in chosen_performance]
            reasoning = assignment.reasoning
        except DailyQuotaExhaustedError:
            raise
        except Exception as e:
            log.error("supervisor_error", review_id=review_id, error=str(e)[:300])
            await crud.create_event(
                review_id=review_id,
                event_type="supervisor_error",
                message=f"Supervisor failed ({type(e).__name__}): every file goes to every agent.",
            )
            result["errors"] = [
                AgentError(agent="supervisor", message=f"{type(e).__name__}: {e!s}"[:500])
            ]
    elif files:
        reasoning = "Small pull request: every file goes to every agent."

    log.info(
        "supervisor_assignments",
        review_id=review_id,
        reviewable=len(files),
        skipped=len(skipped),
        quality=len(result["quality_files"]),
        performance=len(result["performance_files"]),
    )
    message = (
        f"{len(files)} file(s) to review: {len(names)} security, "
        f"{len(result['quality_files'])} quality, {len(result['performance_files'])} performance."
    )
    if skipped:
        message += f" {len(skipped)} file(s) skipped."
    await crud.create_event(
        review_id=review_id,
        event_type="supervisor_done",
        message=message,
        data={
            "files_count": len(files),
            "security_files": names,
            "quality_files": result["quality_files"],
            "performance_files": result["performance_files"],
            "skipped_files": skipped,
            "reasoning": reasoning,
        },
    )
    return result
