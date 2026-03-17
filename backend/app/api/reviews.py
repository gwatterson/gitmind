"""Review API endpoints — CRUD, HITL actions, stats, and manual trigger."""

import os
import structlog
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.config import settings
from app.db import crud
from app.graph.graph import run_review
from app.rate_limiter import rate_limiter

router = APIRouter()
log = structlog.get_logger()


# ──────────────────────────────────────────────
# Request/Response Models
# ──────────────────────────────────────────────

class ManualReviewRequest(BaseModel):
    """Request body for manually triggering a review."""
    repo: str
    pr_number: int

class FindingUpdate(BaseModel):
    """Request body for editing a finding (HITL)."""
    message: Optional[str] = None
    suggestion: Optional[str] = None
    severity: Optional[str] = None


# ──────────────────────────────────────────────
# Review Endpoints
# ──────────────────────────────────────────────

@router.get("/api/reviews")
async def list_reviews(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None),
    repo: Optional[str] = Query(None),
):
    """List reviews with pagination and optional filters."""
    reviews = await crud.list_reviews(limit=limit, offset=offset, status=status, repo=repo)
    return {"reviews": reviews, "count": len(reviews)}


@router.get("/api/reviews/{review_id}")
async def get_review(review_id: str):
    """Get review detail with findings."""
    review = await crud.get_review(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    findings = await crud.get_findings(review_id)
    events = await crud.get_events(review_id)

    return {
        "review": review,
        "findings": findings,
        "events": events,
    }


@router.get("/api/reviews/{review_id}/diff")
async def get_review_diff(review_id: str):
    """Fetch the PR diff dynamically from GitHub for the frontend viewer."""
    review = await crud.get_review(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    from app.mcp_server.server import handle_get_pr_diff
    try:
        diff_result = await handle_get_pr_diff({"repo": review["repo"], "pr_number": review["pr_number"]})
        
        files = []
        for f in diff_result.get("files", []):
            files.append({
                "filename": f.get("filename"),
                "patch": f.get("patch", "")
            })
            
        return {"files": files}
        
    except Exception as e:
        log.error("failed_to_fetch_diff", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to fetch diff: {str(e)}")


@router.get("/api/stats")
async def get_stats():
    """Get aggregate metrics for the dashboard."""
    stats = await crud.get_review_stats()
    return stats


# ──────────────────────────────────────────────
# HITL Endpoints
# ──────────────────────────────────────────────

@router.post("/api/reviews/{review_id}/approve")
async def approve_review(review_id: str):
    """Approve findings and trigger posting to GitHub (HITL)."""
    review = await crud.get_review(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    if review["status"] != "hitl_pending":
        raise HTTPException(status_code=400, detail="Review is not pending HITL approval")

    github_posted = False
    github_warning = None

    from app.mcp_server.server import _get_github_client
    gh = _get_github_client()
    if not gh:
        github_warning = "GitHub client not configured — review approved locally but not posted to GitHub."
        log.warning("approve_without_github", review_id=review_id)
    else:
        try:
            repo = gh.get_repo(review["repo"])
            pr = repo.get_pull(review["pr_number"])
            commit = repo.get_commit(review["commit_id"]) if review.get("commit_id") else pr.get_commits().reversed[0]

            findings = await crud.get_findings(review_id)

            # Post inline comments
            for f in findings:
                if f.get("posted_to_github"):
                    continue

                body = f"**[{f['category'].upper()} - {f['severity'].upper()}]**\n{f['message']}"
                if f.get("suggestion"):
                    body += f"\n\n**Suggestion:**\n```\n{f['suggestion']}\n```"

                try:
                    if f.get("line"):
                        comment = pr.create_review_comment(
                            body=body,
                            commit=commit,
                            path=f["file"],
                            line=int(f["line"]),
                            side="RIGHT"
                        )
                        await crud.update_finding(f["id"], posted_to_github=True, github_comment_id=str(comment.id))
                except Exception as e:
                    log.warning("failed_to_post_inline_comment", finding_id=f["id"], error=str(e))

            # Post summary review
            event_map = {"request_changes": "REQUEST_CHANGES", "approve": "APPROVE", "comment": "COMMENT"}
            event = event_map.get(review.get("verdict", "comment").lower(), "COMMENT")

            pr.create_review(
                body=review.get("summary", "Review completed by GitMind."),
                event=event
            )
            github_posted = True
        except Exception as e:
            log.error("github_post_error", review_id=review_id, error=str(e))
            github_warning = f"Review approved locally but GitHub posting failed: {str(e)}"

    await crud.update_review(review_id, status="completed", completed_at="datetime('now')")
    await crud.create_event(
        review_id=review_id,
        event_type="hitl_approved",
        message="Review approved by user" + (" and posted to GitHub." if github_posted else " (local only)."),
    )

    result = {"status": "approved", "review_id": review_id, "github_posted": github_posted}
    if github_warning:
        result["warning"] = github_warning
    return result


@router.patch("/api/reviews/{review_id}/findings/{finding_id}")
async def update_finding(review_id: str, finding_id: str, body: FindingUpdate):
    """Edit a finding before posting (HITL)."""
    review = await crud.get_review(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    update_data = {k: v for k, v in body.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    finding = await crud.update_finding(finding_id, **update_data)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    return {"finding": finding}


# ──────────────────────────────────────────────
# Rate Limiter
# ──────────────────────────────────────────────

@router.get("/api/rate-limit/status")
async def rate_limit_status():
    """Returns the current rate limiter state for the frontend."""
    return await rate_limiter.get_status()


# ──────────────────────────────────────────────
# Health Check
# ──────────────────────────────────────────────

@router.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "llm_model": settings.GEMINI_MODEL,
        "rate_limiter": await rate_limiter.get_status(),
        "hitl_enabled": settings.HITL_ENABLED,
    }


# ──────────────────────────────────────────────
# Archive Management
# ──────────────────────────────────────────────

@router.delete("/api/reviews")
async def clear_archive():
    """Clear all stored reviews and findings without resetting rate limits."""
    await crud.clear_all_reviews()
    return {"status": "ok", "message": "Archive cleared successfully."}


# ──────────────────────────────────────────────
# Manual Trigger (for testing without webhooks)
# ──────────────────────────────────────────────

@router.get("/api/debug-env")
async def debug_env():
    return {
        "APP_ID": repr(settings.GITHUB_APP_ID),
        "PRIV_KEY": repr(settings.GITHUB_PRIVATE_KEY_PATH),
        "TOKEN": repr(settings.GITHUB_TOKEN),
        "TOKEN_LEN": len(settings.GITHUB_TOKEN)
    }

@router.post("/api/reviews/trigger")
async def trigger_manual_review(body: ManualReviewRequest):
    """
    Manually trigger a review of a PR (for testing without GitHub webhooks).
    Requires GITHUB_TOKEN env var or GitHub App credentials.
    """
    from app.mcp_server.server import handle_get_pr_diff, handle_get_pr_metadata

    log.info("DEBUG_GITHUB_AUTH",
             app_id=repr(settings.GITHUB_APP_ID),
             priv_key_path=repr(settings.GITHUB_PRIVATE_KEY_PATH),
             token_length=len(settings.GITHUB_TOKEN))

    log.info("manual_review_triggered", repo=body.repo, pr_number=body.pr_number)

    try:
        # Fetch PR metadata
        metadata = await handle_get_pr_metadata({"repo": body.repo, "pr_number": body.pr_number})
        if "error" in metadata:
            raise HTTPException(status_code=400, detail=f"GitHub error: {metadata['error']}")

        # Fetch PR diff
        diff_result = await handle_get_pr_diff({"repo": body.repo, "pr_number": body.pr_number})
        if "error" in diff_result:
            raise HTTPException(status_code=400, detail=f"GitHub error: {diff_result['error']}")

        commit_id = ""  # Will be fetched from the PR
        files = []
        for f in diff_result.get("files", []):
            ext = os.path.splitext(f.get("filename", ""))[1].lower()
            lang_map = {".py": "python", ".js": "javascript", ".ts": "typescript",
                        ".jsx": "javascript", ".tsx": "typescript"}
            files.append({
                "filename": f["filename"],
                "language": lang_map.get(ext, "unknown"),
                "patch": f.get("patch", ""),
                "additions": f.get("additions", 0),
                "deletions": f.get("deletions", 0),
            })

        # Create review
        review = await crud.create_review(
            repo=body.repo,
            pr_number=body.pr_number,
            pr_title=metadata.get("title", ""),
            pr_author=metadata.get("author", ""),
            commit_id=commit_id,
        )

        # Run review (async task in background)
        import asyncio
        asyncio.create_task(run_review(
            review_id=review["id"],
            repo=body.repo,
            pr_number=body.pr_number,
            commit_id=commit_id,
            files=files,
            pr_metadata=metadata,
        ))

        return {"review_id": review["id"], "status": "queued", "files_count": len(files)}

    except HTTPException:
        raise
    except Exception as e:
        log.error("manual_review_error", error=str(e))
        error_msg = str(e)
        if "404" in error_msg and "Not Found" in error_msg:
            error_msg = "Repository or PR not found (or no access with current token)."
        elif "401" in error_msg or "Bad credentials" in error_msg:
            error_msg = "GitHub authentication failed. Check your token/app configuration."
        raise HTTPException(status_code=500, detail=error_msg)
