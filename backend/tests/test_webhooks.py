"""GitHub webhook endpoint: signature, idempotency, filtering and scheduling."""

import hashlib
import hmac
import json
from typing import Any

import pytest

from app.config import settings
from app.db import crud
from app.services import review_runner

SECRET = "test-webhook-secret"


@pytest.fixture
def started(monkeypatch) -> list[str]:
    """Capture scheduled reviews instead of running them."""
    review_ids: list[str] = []

    def fake_start(review_id, coro):
        coro.close()  # never awaited: avoid touching GitHub or the LLM
        review_ids.append(review_id)

    monkeypatch.setattr(review_runner, "start", fake_start)
    return review_ids


def _pr_payload(action: str = "opened", sha: str = "abc123", draft: bool = False) -> dict:
    return {
        "action": action,
        "repository": {"full_name": "octo/demo"},
        "pull_request": {
            "number": 7,
            "title": "Add feature",
            "draft": draft,
            "user": {"login": "dev"},
            "head": {"sha": sha, "ref": "feature"},
            "base": {"ref": "main"},
        },
    }


async def _deliver(
    client,
    payload: Any,
    event: str = "pull_request",
    delivery: str = "d-1",
    secret: str = SECRET,
    signature: str | None = None,
):
    body = json.dumps(payload).encode()
    if signature is None:
        signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return await client.post(
        "/webhook/github",
        content=body,
        headers={
            "X-Hub-Signature-256": signature,
            "X-GitHub-Event": event,
            "X-GitHub-Delivery": delivery,
            "Content-Type": "application/json",
        },
    )


async def test_valid_pull_request_is_queued(client, started):
    response = await _deliver(client, _pr_payload())
    assert response.status_code == 200
    assert response.json()["status"] == "queued"
    assert started == [response.json()["review_id"]]

    review = await crud.get_review(started[0])
    assert review is not None
    assert review["commit_id"] == "abc123"


async def test_missing_or_wrong_signature_is_rejected(client, started):
    unsigned = await _deliver(client, _pr_payload(), signature="")
    wrong = await _deliver(client, _pr_payload(), secret="another-secret", delivery="d-2")
    assert unsigned.status_code == 401
    assert wrong.status_code == 401
    assert started == []


async def test_webhook_fails_closed_without_configured_secret(client, started, monkeypatch):
    monkeypatch.setattr(settings, "GITHUB_WEBHOOK_SECRET", type(settings.GITHUB_WEBHOOK_SECRET)(""))
    # Even a payload "signed" with an empty key must be refused
    response = await _deliver(client, _pr_payload(), secret="")
    assert response.status_code == 401
    assert started == []


async def test_redelivered_event_is_processed_once(client, started):
    first = await _deliver(client, _pr_payload(), delivery="same-id")
    second = await _deliver(client, _pr_payload(sha="other"), delivery="same-id")
    assert first.json()["status"] == "queued"
    assert second.json()["status"] == "duplicate"
    assert len(started) == 1


async def test_same_commit_is_not_reviewed_twice(client, started):
    await _deliver(client, _pr_payload(), delivery="a")
    again = await _deliver(client, _pr_payload(action="reopened"), delivery="b")
    assert again.json()["status"] == "duplicate"
    assert len(started) == 1


async def test_new_commit_supersedes_the_running_review(client, started):
    first = await _deliver(client, _pr_payload(sha="old"), delivery="a")
    second = await _deliver(client, _pr_payload(action="synchronize", sha="new"), delivery="b")

    old_review = await crud.get_review(first.json()["review_id"])
    new_review = await crud.get_review(second.json()["review_id"])
    assert old_review is not None and old_review["status"] == "superseded"
    assert new_review is not None and new_review["status"] == "pending"


@pytest.mark.parametrize("action", ["opened", "synchronize", "reopened", "ready_for_review"])
async def test_review_actions_are_handled(client, started, action):
    response = await _deliver(client, _pr_payload(action=action), delivery=f"d-{action}")
    assert response.json()["status"] == "queued"


async def test_other_actions_and_events_are_ignored(client, started):
    closed = await _deliver(client, _pr_payload(action="closed"), delivery="a")
    issue = await _deliver(client, {"action": "opened"}, event="issues", delivery="b")
    ping = await _deliver(client, {"zen": "hi"}, event="ping", delivery="c")
    assert closed.json()["status"] == "ignored"
    assert issue.json()["status"] == "ignored"
    assert ping.json()["status"] == "pong"
    assert started == []


async def test_draft_pull_requests_are_skipped_by_default(client, started, monkeypatch):
    skipped = await _deliver(client, _pr_payload(draft=True), delivery="a")
    assert skipped.json()["status"] == "ignored"

    monkeypatch.setattr(settings, "REVIEW_DRAFT_PRS", True)
    reviewed = await _deliver(client, _pr_payload(draft=True, sha="x"), delivery="b")
    assert reviewed.json()["status"] == "queued"


async def test_oversized_payload_is_rejected(client, started, monkeypatch):
    monkeypatch.setattr(settings, "WEBHOOK_MAX_BODY_BYTES", 100)
    response = await _deliver(client, _pr_payload())
    assert response.status_code == 413
    assert started == []


async def test_invalid_json_is_rejected(client, started):
    body = b"not json"
    signature = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    response = await client.post(
        "/webhook/github",
        content=body,
        headers={"X-Hub-Signature-256": signature, "X-GitHub-Event": "pull_request"},
    )
    assert response.status_code == 400
