"""Review API: HITL approval, finding ownership, manual trigger, error handling, headers."""

from unittest.mock import AsyncMock

import pytest
from github import GithubException

from app.api import reviews as reviews_api
from app.config import settings
from app.db import crud
from app.main import create_app
from app.services import publisher, review_runner
from app.services.publisher import PublishResult


async def _review(status: str = "hitl_pending") -> dict:
    review = await crud.create_review(repo="octo/demo", pr_number=3, commit_id="sha1")
    await crud.update_review(review["id"], status=status, verdict="comment", summary="ok")
    return review


async def _finding(review_id: str) -> dict:
    [finding] = await crud.create_findings_batch(
        review_id,
        [
            {
                "file": "a.py",
                "line": 3,
                "severity": "high",
                "category": "security",
                "message": "SQL injection",
                "agent": "security",
            }
        ],
    )
    return finding


# ──────────────────────────────────────────────
# HITL approval
# ──────────────────────────────────────────────


async def test_approve_publishes_and_completes(user_client, monkeypatch):
    review = await _review()
    publish = AsyncMock(return_value=PublishResult(posted=True, comments_posted=2))
    monkeypatch.setattr(publisher, "publish_review", publish)

    response = await user_client.post(f"/api/reviews/{review['id']}/approve")

    assert response.status_code == 200
    assert response.json()["github_posted"] is True
    publish.assert_awaited_once_with(review["id"], human_approved=True)
    stored = await crud.get_review(review["id"])
    assert stored is not None
    assert stored["status"] == "completed"
    assert stored["completed_at"] and not stored["completed_at"].startswith("datetime")


async def test_approve_keeps_review_pending_when_github_fails(user_client, monkeypatch):
    review = await _review()
    failure = PublishResult(posted=False, warning="Posting to GitHub failed.", retryable=True)
    monkeypatch.setattr(publisher, "publish_review", AsyncMock(return_value=failure))

    response = await user_client.post(f"/api/reviews/{review['id']}/approve")

    assert response.status_code == 502
    stored = await crud.get_review(review["id"])
    assert stored is not None and stored["status"] == "hitl_pending"


async def test_approve_rejects_reviews_not_pending(user_client):
    review = await _review(status="completed")
    response = await user_client.post(f"/api/reviews/{review['id']}/approve")
    assert response.status_code == 409


async def test_finding_can_only_be_edited_through_its_own_review(user_client):
    review = await _review()
    other = await _review()
    finding = await _finding(review["id"])

    wrong = await user_client.patch(
        f"/api/reviews/{other['id']}/findings/{finding['id']}", json={"message": "x"}
    )
    right = await user_client.patch(
        f"/api/reviews/{review['id']}/findings/{finding['id']}", json={"message": "edited"}
    )

    assert wrong.status_code == 404
    assert right.status_code == 200
    assert right.json()["finding"]["message"] == "edited"


async def test_findings_are_sorted_by_severity(user_client):
    review = await _review()
    await crud.create_findings_batch(
        review["id"],
        [
            {"file": "a.py", "severity": sev, "category": "quality", "message": sev, "agent": "q"}
            for sev in ["low", "critical", "info", "medium", "high"]
        ],
    )
    response = await user_client.get(f"/api/reviews/{review['id']}")
    severities = [f["severity"] for f in response.json()["findings"]]
    assert severities == ["critical", "high", "medium", "low", "info"]


# ──────────────────────────────────────────────
# Manual trigger
# ──────────────────────────────────────────────


@pytest.fixture
def started(monkeypatch) -> list[str]:
    review_ids: list[str] = []

    def fake_start(review_id, coro):
        coro.close()
        review_ids.append(review_id)

    monkeypatch.setattr(review_runner, "start", fake_start)
    return review_ids


def _metadata(**overrides):
    data = {"title": "T", "author": "dev", "head_sha": "headsha", "base_branch": "main"}
    data.update(overrides)
    return AsyncMock(return_value=data)


async def test_trigger_uses_the_pr_head_commit(user_client, started, monkeypatch):
    monkeypatch.setattr(reviews_api, "handle_get_pr_metadata", _metadata())

    response = await user_client.post(
        "/api/reviews/trigger", json={"repo": "octo/demo", "pr_number": 3}
    )

    assert response.status_code == 202
    review = await crud.get_review(response.json()["review_id"])
    assert review is not None and review["commit_id"] == "headsha"
    assert started == [review["id"]]


async def test_trigger_refuses_a_commit_already_in_review(user_client, started, monkeypatch):
    monkeypatch.setattr(reviews_api, "handle_get_pr_metadata", _metadata())
    await user_client.post("/api/reviews/trigger", json={"repo": "octo/demo", "pr_number": 3})
    again = await user_client.post(
        "/api/reviews/trigger", json={"repo": "octo/demo", "pr_number": 3}
    )
    assert again.status_code == 409


async def test_trigger_hides_internal_github_errors(user_client, started, monkeypatch):
    error = GithubException(500, {"message": "token ghp_abcdefghijklmnopqrstuvwxyz0123"}, None)
    monkeypatch.setattr(reviews_api, "handle_get_pr_metadata", AsyncMock(side_effect=error))

    response = await user_client.post(
        "/api/reviews/trigger", json={"repo": "octo/demo", "pr_number": 3}
    )

    assert response.status_code == 502
    assert "ghp_" not in response.text
    assert "Reference id" in response.json()["detail"]


async def test_trigger_reports_missing_pr_as_404(user_client, started, monkeypatch):
    error = GithubException(404, {"message": "Not Found"}, None)
    monkeypatch.setattr(reviews_api, "handle_get_pr_metadata", AsyncMock(side_effect=error))
    response = await user_client.post(
        "/api/reviews/trigger", json={"repo": "octo/demo", "pr_number": 3}
    )
    assert response.status_code == 404


async def test_trigger_is_rate_limited(user_client, started, monkeypatch):
    monkeypatch.setattr(reviews_api, "handle_get_pr_metadata", _metadata(head_sha=""))
    statuses = []
    for _ in range(11):
        response = await user_client.post(
            "/api/reviews/trigger", json={"repo": "octo/demo", "pr_number": 3}
        )
        statuses.append(response.status_code)
    assert statuses[:10] == [202] * 10
    assert statuses[10] == 429


# ──────────────────────────────────────────────
# HTTP hardening
# ──────────────────────────────────────────────


async def test_security_headers_are_set(client):
    response = await client.get("/api/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


async def test_stream_requires_authentication(client):
    review = await _review()
    anonymous = await client.get(f"/api/stream/{review['id']}")
    assert anonymous.status_code == 401


async def test_stream_replays_events_without_wildcard_cors(user_client):
    review = await _review()
    await crud.create_event(review["id"], "review_complete", "done")

    response = await user_client.get(f"/api/stream/{review['id']}")

    assert response.status_code == 200
    assert "review_complete" in response.text
    assert "stream_end" in response.text
    assert "access-control-allow-origin" not in response.headers


async def test_stream_of_unknown_review_is_404(user_client):
    response = await user_client.get("/api/stream/does-not-exist")
    assert response.status_code == 404


async def test_docs_are_disabled_in_production(monkeypatch):
    import httpx

    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        assert (await c.get("/docs")).status_code == 404
        assert (await c.get("/openapi.json")).status_code == 404
        response = await c.get("/api/health")
        assert "Strict-Transport-Security" in response.headers


async def test_unhandled_errors_return_an_opaque_reference(monkeypatch):
    import httpx

    from app.core.security import SESSION_COOKIE
    from app.main import app
    from tests.conftest import session_token

    monkeypatch.setattr(crud, "get_review_stats", AsyncMock(side_effect=RuntimeError("db secret")))
    # Starlette re-raises after sending the 500 response, so the server can log it
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        c.cookies.set(SESSION_COOKIE, session_token("alice"))
        response = await c.get("/api/stats")
    assert response.status_code == 500
    assert "db secret" not in response.text
    assert "Reference id" in response.json()["detail"]
