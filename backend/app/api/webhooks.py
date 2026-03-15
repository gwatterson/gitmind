"""GitHub webhook handler with HMAC-SHA256 validation."""

import hashlib
import hmac
import structlog
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks

from app.config import settings
from app.db import crud
from app.graph.graph import run_review

router = APIRouter()
log = structlog.get_logger()


def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Validate GitHub webhook HMAC-SHA256 signature (timing-safe)."""
    if not signature or not secret:
        return False
    expected = "sha256=" + hmac.new(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


async def _run_review_from_webhook(review_id: str, payload: dict):
    """Background task: fetch PR files and run the review graph."""
    try:
        pr = payload.get("pull_request", {})
        repo_name = payload.get("repository", {}).get("full_name", "")
        pr_number = pr.get("number", 0)
        commit_id = pr.get("head", {}).get("sha", "")

        # Fetch PR files via GitHub API
        from app.mcp_server.server import handle_get_pr_diff
        diff_result = await handle_get_pr_diff({"repo": repo_name, "pr_number": pr_number})

        files = []
        for f in diff_result.get("files", []):
            import os
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

        pr_metadata = {
            "title": pr.get("title", ""),
            "author": pr.get("user", {}).get("login", ""),
            "base_branch": pr.get("base", {}).get("ref", ""),
            "head_branch": pr.get("head", {}).get("ref", ""),
        }

        await run_review(
            review_id=review_id,
            repo=repo_name,
            pr_number=pr_number,
            commit_id=commit_id,
            files=files,
            pr_metadata=pr_metadata,
        )
    except Exception as e:
        log.error("webhook_review_failed", review_id=review_id, error=str(e))
        await crud.update_review(review_id, status="failed", error=str(e))


@router.post("/webhook/github")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    """Receive and process GitHub webhook events."""
    # 1. Validate HMAC-SHA256 signature
    signature = request.headers.get("X-Hub-Signature-256", "")
    body = await request.body()

    if settings.GITHUB_WEBHOOK_SECRET:
        if not verify_signature(body, signature, settings.GITHUB_WEBHOOK_SECRET):
            log.warning("webhook_invalid_signature")
            raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    event = request.headers.get("X-GitHub-Event", "")

    log.info("webhook_received", event=event, action=payload.get("action", ""))

    # 2. Process only PR opened/synchronize events
    if event == "pull_request" and payload.get("action") in ("opened", "synchronize"):
        pr = payload.get("pull_request", {})
        repo_name = payload.get("repository", {}).get("full_name", "")
        pr_number = pr.get("number", 0)
        commit_id = pr.get("head", {}).get("sha", "")

        # Dedup check
        is_dup = await crud.check_duplicate_review(repo_name, commit_id)
        if is_dup:
            log.info("webhook_duplicate", repo=repo_name, commit_id=commit_id)
            return {"status": "duplicate", "message": "Review already in progress for this commit"}

        # Create review
        review = await crud.create_review(
            repo=repo_name,
            pr_number=pr_number,
            pr_title=pr.get("title", ""),
            pr_author=pr.get("user", {}).get("login", ""),
            commit_id=commit_id,
        )

        # Launch review in background
        background_tasks.add_task(_run_review_from_webhook, review["id"], payload)

        return {"review_id": review["id"], "status": "queued"}

    return {"status": "ignored", "event": event}
