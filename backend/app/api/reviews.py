"""Review API endpoints: CRUD, HITL actions, stats, and manual trigger."""

import asyncio
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.config import settings
from app.core.errors import github_error, internal_error
from app.core.ratelimit import limiter
from app.core.security import Principal, require_admin, require_read, require_write
from app.db import crud
from app.mcp_server.server import handle_get_pr_diff, handle_get_pr_metadata
from app.rate_limiter import rate_limiter
from app.services import publisher, review_runner

router = APIRouter(tags=["reviews"])
log = structlog.get_logger()


# ──────────────────────────────────────────────
# Request models
# ──────────────────────────────────────────────


class ManualReviewRequest(BaseModel):
    """Request body for manually triggering a review."""

    repo: str = Field(..., max_length=200, pattern=r"^[a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+$")
    pr_number: int = Field(..., gt=0)


class FindingUpdate(BaseModel):
    """Request body for editing a finding (HITL)."""

    message: str | None = Field(None, max_length=10000)
    suggestion: str | None = Field(None, max_length=10000)
    severity: str | None = Field(None, pattern=r"^(critical|high|medium|low|info)$")


async def _get_review_or_404(review_id: str) -> dict[str, Any]:
    review = await crud.get_review(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    return review


# ──────────────────────────────────────────────
# Review endpoints
# ──────────────────────────────────────────────


@router.get("/api/reviews")
async def list_reviews(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None, max_length=32),
    repo: str | None = Query(None, max_length=200),
    _: Principal = Depends(require_read),
) -> dict[str, Any]:
    """List reviews with pagination and optional filters."""
    reviews = await crud.list_reviews(limit=limit, offset=offset, status=status, repo=repo)
    return {"reviews": reviews, "count": len(reviews)}


@router.get("/api/reviews/{review_id}")
async def get_review(review_id: str, _: Principal = Depends(require_read)) -> dict[str, Any]:
    """Get review detail with findings and events."""
    review = await _get_review_or_404(review_id)
    return {
        "review": review,
        "findings": await crud.get_findings(review_id),
        "events": await crud.get_events(review_id),
    }


@router.delete("/api/reviews/{review_id}")
async def delete_review(review_id: str, _: Principal = Depends(require_write)) -> dict[str, str]:
    """Delete a review and all its associated findings/events."""
    await _get_review_or_404(review_id)
    review_runner.cancel(review_id)
    if not await crud.delete_review(review_id):
        raise HTTPException(status_code=404, detail="Review not found")
    return {"status": "ok", "message": "Review deleted"}


@router.get("/api/reviews/{review_id}/diff")
async def get_review_diff(review_id: str, _: Principal = Depends(require_read)) -> dict[str, Any]:
    """Fetch the PR diff from GitHub for the frontend viewer."""
    review = await _get_review_or_404(review_id)
    try:
        diff_result = await handle_get_pr_diff(
            {"repo": review["repo"], "pr_number": review["pr_number"]}
        )
    except Exception as e:
        raise github_error("failed_to_fetch_diff", e) from e
    if "error" in diff_result:
        raise HTTPException(status_code=503, detail="GitHub client not configured")

    files = [
        {"filename": f.get("filename"), "patch": f.get("patch", "")}
        for f in diff_result.get("files", [])
    ]
    return {"files": files}


@router.get("/api/stats")
async def get_stats(_: Principal = Depends(require_read)) -> dict[str, Any]:
    """Get aggregate metrics for the dashboard."""
    return await crud.get_review_stats()


# ──────────────────────────────────────────────
# HITL endpoints
# ──────────────────────────────────────────────


@router.post("/api/reviews/{review_id}/approve")
async def approve_review(
    review_id: str, principal: Principal = Depends(require_write)
) -> dict[str, Any]:
    """Approve the findings and post the review to GitHub (HITL)."""
    review = await _get_review_or_404(review_id)
    if review["status"] != "hitl_pending":
        raise HTTPException(status_code=409, detail="Review is not pending HITL approval")

    result = await publisher.publish_review(review_id, human_approved=True)
    if result.retryable:
        # Keep the review pending so the user can retry once GitHub is reachable
        raise HTTPException(status_code=502, detail=result.warning)

    await crud.update_review(review_id, status="completed", completed_at=crud.utc_now())
    await crud.create_event(
        review_id=review_id,
        event_type="hitl_approved",
        message=f"Review approved by {principal.login}"
        + (" and posted to GitHub." if result.posted else " (not posted to GitHub)."),
    )

    response: dict[str, Any] = {
        "status": "approved",
        "review_id": review_id,
        "github_posted": result.posted,
    }
    if result.warning:
        response["warning"] = result.warning
    return response


@router.patch("/api/reviews/{review_id}/findings/{finding_id}")
async def update_finding(
    review_id: str,
    finding_id: str,
    body: FindingUpdate,
    _: Principal = Depends(require_write),
) -> dict[str, Any]:
    """Edit a finding before posting (HITL)."""
    await _get_review_or_404(review_id)
    existing = await crud.get_finding(finding_id)
    # The finding must belong to the review in the URL
    if not existing or existing["review_id"] != review_id:
        raise HTTPException(status_code=404, detail="Finding not found")

    update_data = {k: v for k, v in body.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    return {"finding": await crud.update_finding(finding_id, **update_data)}


# ──────────────────────────────────────────────
# Monitoring
# ──────────────────────────────────────────────


@router.get("/api/rate-limit/status")
async def rate_limit_status(_: Principal = Depends(require_read)) -> dict[str, Any]:
    """Return the current LLM rate limiter state for the dashboard."""
    return await rate_limiter.get_status()


@router.get("/api/health")
@limiter.exempt
async def health_check() -> dict[str, str]:
    """Public liveness probe. Exposes no internal state."""
    return {"status": "ok"}


# ──────────────────────────────────────────────
# Archive management
# ──────────────────────────────────────────────


@router.delete("/api/reviews")
async def clear_archive(principal: Principal = Depends(require_admin)) -> dict[str, str]:
    """Delete all stored reviews and findings (administrators only)."""
    await crud.clear_all_reviews()
    log.warning("archive_cleared", by=principal.login)
    return {"status": "ok", "message": "Archive cleared successfully."}


# ──────────────────────────────────────────────
# Manual trigger (for testing without webhooks)
# ──────────────────────────────────────────────


@router.post("/api/reviews/trigger", status_code=202)
@limiter.limit(settings.HTTP_RATE_LIMIT_TRIGGER)
async def trigger_manual_review(
    request: Request,
    body: ManualReviewRequest,
    _: Principal = Depends(require_write),
) -> dict[str, Any]:
    """Manually trigger a review of a PR. Requires GitHub credentials on the server."""
    log.info("manual_review_triggered", repo=body.repo, pr_number=body.pr_number)

    try:
        metadata = await handle_get_pr_metadata({"repo": body.repo, "pr_number": body.pr_number})
    except Exception as e:
        raise github_error("manual_review_metadata_failed", e) from e
    if "error" in metadata:
        raise HTTPException(status_code=503, detail="GitHub client not configured")

    commit_id = metadata.get("head_sha", "")
    if commit_id and await crud.check_duplicate_review(body.repo, commit_id):
        raise HTTPException(
            status_code=409, detail="A review of this commit is already in progress"
        )

    try:
        review = await crud.create_review(
            repo=body.repo,
            pr_number=body.pr_number,
            pr_title=metadata.get("title", ""),
            pr_author=metadata.get("author", ""),
            commit_id=commit_id,
        )
        await review_runner.supersede_previous(body.repo, body.pr_number, review["id"])
    except Exception as e:
        raise internal_error("manual_review_create_failed", e) from e

    review_runner.start(
        review["id"],
        review_runner.fetch_and_run(review["id"], body.repo, body.pr_number, commit_id, metadata),
    )
    # Yield once so the background task starts before the response is sent
    await asyncio.sleep(0)
    return {"review_id": review["id"], "status": "queued"}
