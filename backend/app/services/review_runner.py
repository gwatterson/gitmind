"""Starts and tracks review runs in the background.

Runs live in this process only; a durable job queue replaces this in PLAN.md F4.4.
"""

import asyncio
from collections.abc import Coroutine
from typing import Any

import structlog

from app.db import crud
from app.diff.files import detect_language
from app.graph.graph import run_review
from app.graph.state import PRFile
from app.mcp_server.server import handle_get_pr_diff

log = structlog.get_logger()


# review_id -> running task. Also keeps strong references so tasks are not
# garbage collected before they finish.
_tasks: dict[str, asyncio.Task[Any]] = {}


def build_pr_files(diff_files: list[dict[str, Any]]) -> list[PRFile]:
    """Convert GitHub diff entries into the pipeline's file format."""
    files: list[PRFile] = []
    for f in diff_files:
        files.append(
            PRFile(
                filename=f["filename"],
                language=detect_language(f["filename"]),
                patch=f.get("patch", ""),
                additions=f.get("additions", 0),
                deletions=f.get("deletions", 0),
            )
        )
    return files


def start(review_id: str, coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
    task = asyncio.create_task(coro, name=f"review-{review_id}")
    _tasks[review_id] = task
    task.add_done_callback(lambda _: _tasks.pop(review_id, None))
    return task


def cancel(review_id: str) -> bool:
    """Cancel a running review. Returns True if a task was running."""
    task = _tasks.get(review_id)
    if task is None or task.done():
        return False
    task.cancel()
    return True


async def supersede_previous(repo: str, pr_number: int, new_review_id: str) -> list[str]:
    """Stop in-flight reviews of the same PR: a newer commit makes them obsolete."""
    superseded = await crud.supersede_active_reviews(repo, pr_number, new_review_id)
    for review_id in superseded:
        cancel(review_id)
        await crud.create_event(
            review_id=review_id,
            event_type="review_error",
            message="Superseded by a newer commit on the same pull request.",
        )
    if superseded:
        log.info("reviews_superseded", repo=repo, pr_number=pr_number, review_ids=superseded)
    return superseded


async def fetch_and_run(
    review_id: str,
    repo: str,
    pr_number: int,
    commit_id: str,
    pr_metadata: dict[str, Any],
) -> None:
    """Fetch the PR diff from GitHub and run the review graph."""
    try:
        diff_result = await handle_get_pr_diff({"repo": repo, "pr_number": pr_number})
        if "error" in diff_result:
            raise RuntimeError(diff_result["error"])
        await run_review(
            review_id=review_id,
            repo=repo,
            pr_number=pr_number,
            commit_id=commit_id,
            files=build_pr_files(diff_result.get("files", [])),
            pr_metadata=pr_metadata,
        )
    except asyncio.CancelledError:
        log.info("review_cancelled", review_id=review_id)
        raise
    except Exception as e:
        log.error(
            "review_run_failed", review_id=review_id, error_type=type(e).__name__, error=str(e)
        )
        await crud.update_review(
            review_id,
            status="failed",
            error="Could not fetch the pull request from GitHub.",
            completed_at=crud.utc_now(),
        )
        await crud.create_event(
            review_id=review_id,
            event_type="review_error",
            message="Review failed: could not fetch the pull request from GitHub.",
        )
