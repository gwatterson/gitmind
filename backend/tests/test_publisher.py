"""Publishing reviews to GitHub (PyGithub is replaced by mocks)."""

from unittest.mock import MagicMock

import pytest

from app.config import settings
from app.db import crud
from app.services import publisher


@pytest.mark.parametrize(
    ("verdict", "human", "allow", "expected"),
    [
        ("request_changes", False, False, "REQUEST_CHANGES"),
        ("comment", False, False, "COMMENT"),
        ("approve", False, False, "COMMENT"),
        ("approve", True, False, "COMMENT"),
        ("approve", False, True, "COMMENT"),
        ("approve", True, True, "APPROVE"),
        (None, False, False, "COMMENT"),
    ],
)
def test_bot_never_approves_on_its_own(monkeypatch, verdict, human, allow, expected):
    monkeypatch.setattr(settings, "ALLOW_BOT_APPROVE", allow)
    assert publisher.github_review_event(verdict, human) == expected


async def _review_with_findings(status: str = "completed") -> dict:
    review = await crud.create_review(repo="octo/demo", pr_number=5, commit_id="sha")
    await crud.update_review(review["id"], status=status, verdict="approve", summary="All good")
    await crud.create_findings_batch(
        review["id"],
        [
            {
                "file": "a.py",
                "line": 4,
                "severity": "low",
                "category": "quality",
                "message": "m1",
                "agent": "q",
            },
            {
                "file": "b.py",
                "line": 0,
                "severity": "info",
                "category": "quality",
                "message": "no line",
                "agent": "q",
            },
        ],
    )
    return review


def _fake_github() -> tuple[MagicMock, MagicMock]:
    gh = MagicMock()
    pr = gh.get_repo.return_value.get_pull.return_value
    pr.create_review_comment.return_value.id = 99
    return gh, pr


async def test_publish_posts_inline_comments_and_summary(monkeypatch):
    review = await _review_with_findings()
    gh, pr = _fake_github()
    monkeypatch.setattr(publisher, "get_github_client", lambda: gh)

    result = await publisher.publish_review(review["id"], human_approved=False)

    assert result.posted is True
    assert result.comments_posted == 1  # the finding without a line is skipped
    pr.create_review.assert_called_once_with(body="All good", event="COMMENT")
    findings = await crud.get_findings(review["id"])
    posted = [f for f in findings if f["posted_to_github"]]
    assert len(posted) == 1 and posted[0]["github_comment_id"] == "99"


async def test_failed_inline_comment_is_reported_not_fatal(monkeypatch):
    review = await _review_with_findings()
    gh, pr = _fake_github()
    pr.create_review_comment.side_effect = RuntimeError("422 line not in diff")
    monkeypatch.setattr(publisher, "get_github_client", lambda: gh)

    result = await publisher.publish_review(review["id"], human_approved=False)

    assert result.posted is True
    assert result.comments_failed == 1
    assert result.warning and "could not be placed" in result.warning


async def test_missing_github_client_is_a_warning(monkeypatch):
    review = await _review_with_findings()
    monkeypatch.setattr(publisher, "get_github_client", lambda: None)

    result = await publisher.publish_review(review["id"], human_approved=False)

    assert result.posted is False
    assert result.retryable is False
    assert result.warning and "not configured" in result.warning


async def test_github_outage_is_retryable(monkeypatch):
    review = await _review_with_findings()
    gh, pr = _fake_github()
    pr.create_review.side_effect = RuntimeError("502 Bad Gateway")
    monkeypatch.setattr(publisher, "get_github_client", lambda: gh)

    result = await publisher.publish_review(review["id"], human_approved=False)

    assert result.posted is False
    assert result.retryable is True


async def test_superseded_review_is_not_published(monkeypatch):
    review = await _review_with_findings(status="superseded")
    gh, pr = _fake_github()
    monkeypatch.setattr(publisher, "get_github_client", lambda: gh)

    result = await publisher.publish_review(review["id"], human_approved=False)

    assert result.posted is False
    pr.create_review.assert_not_called()
