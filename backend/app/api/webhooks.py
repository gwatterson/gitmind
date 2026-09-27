"""GitHub webhook receiver: HMAC-SHA256 validation, idempotency, review scheduling."""

import hashlib
import hmac
import json
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.core.ratelimit import limiter
from app.db import crud
from app.services import review_runner

router = APIRouter(tags=["webhooks"])
log = structlog.get_logger()

# pull_request actions that should trigger a review
REVIEW_ACTIONS = {"opened", "synchronize", "reopened", "ready_for_review"}


def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Validate the GitHub webhook HMAC-SHA256 signature (timing-safe)."""
    if not signature or not secret:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


async def _read_limited_body(request: Request) -> bytes:
    """Read the body, refusing payloads larger than WEBHOOK_MAX_BODY_BYTES."""
    limit = settings.WEBHOOK_MAX_BODY_BYTES
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            if int(declared) > limit:
                raise HTTPException(status_code=413, detail="Payload too large")
        except ValueError as e:
            raise HTTPException(status_code=400, detail="Invalid Content-Length") from e

    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > limit:
            raise HTTPException(status_code=413, detail="Payload too large")
    return bytes(body)


@router.post("/webhook/github")
@limiter.exempt  # authenticated by signature; GitHub may deliver in bursts
async def github_webhook(request: Request) -> dict[str, Any]:
    """Receive and process GitHub webhook events."""
    body = await _read_limited_body(request)

    # Fail closed: without a configured secret no delivery can be trusted
    secret = settings.GITHUB_WEBHOOK_SECRET.get_secret_value()
    if not secret:
        log.error("webhook_secret_not_configured")
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not verify_signature(body, signature, secret):
        log.warning("webhook_invalid_signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload: dict[str, Any] = json.loads(body)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from e

    event = request.headers.get("X-GitHub-Event", "")
    delivery_id = request.headers.get("X-GitHub-Delivery", "")
    action = payload.get("action", "")
    log.info("webhook_received", webhook_event=event, action=action, delivery_id=delivery_id)

    # GitHub retries failed deliveries: process each delivery id only once
    if delivery_id and not await crud.record_webhook_delivery(delivery_id, event):
        return {"status": "duplicate", "message": "Delivery already processed"}

    if event == "ping":
        return {"status": "pong"}
    if event != "pull_request" or action not in REVIEW_ACTIONS:
        return {"status": "ignored", "event": event, "action": action}

    pr = payload.get("pull_request", {})
    if pr.get("draft") and not settings.REVIEW_DRAFT_PRS:
        return {"status": "ignored", "reason": "draft pull request"}

    repo_name = payload.get("repository", {}).get("full_name", "")
    pr_number = pr.get("number", 0)
    commit_id = pr.get("head", {}).get("sha", "")
    if not repo_name or not pr_number or not commit_id:
        raise HTTPException(status_code=400, detail="Incomplete pull_request payload")

    if await crud.check_duplicate_review(repo_name, commit_id):
        log.info("webhook_duplicate_commit", repo=repo_name, commit_id=commit_id)
        return {"status": "duplicate", "message": "Review already in progress for this commit"}

    review = await crud.create_review(
        repo=repo_name,
        pr_number=pr_number,
        pr_title=pr.get("title", ""),
        pr_author=pr.get("user", {}).get("login", ""),
        commit_id=commit_id,
    )
    await review_runner.supersede_previous(repo_name, pr_number, review["id"])

    pr_metadata = {
        "title": pr.get("title", ""),
        "author": pr.get("user", {}).get("login", ""),
        "base_branch": pr.get("base", {}).get("ref", ""),
        "head_branch": pr.get("head", {}).get("ref", ""),
    }
    review_runner.start(
        review["id"],
        review_runner.fetch_and_run(review["id"], repo_name, pr_number, commit_id, pr_metadata),
    )
    return {"review_id": review["id"], "status": "queued"}
