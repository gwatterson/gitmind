"""Publishes a completed review to GitHub (inline comments plus a summary review)."""

import asyncio
from dataclasses import dataclass, field
from typing import Any

import structlog

from app.config import settings
from app.db import crud
from app.github.client import get_github_client

log = structlog.get_logger()

_VERDICT_TO_EVENT = {"request_changes": "REQUEST_CHANGES", "comment": "COMMENT"}


@dataclass
class PublishResult:
    posted: bool
    warning: str | None = None
    # True when posting failed for a reason worth retrying (e.g. GitHub API error)
    retryable: bool = False
    comments_posted: int = 0
    comments_failed: int = 0
    comment_ids: dict[str, str] = field(default_factory=dict)


def github_review_event(verdict: str | None, human_approved: bool) -> str:
    """Map an internal verdict to a GitHub review event.

    The bot never approves on its own: a prompt-injected PR could otherwise get
    itself approved. APPROVE requires ALLOW_BOT_APPROVE and a human approval.
    """
    verdict = (verdict or "comment").lower()
    if verdict == "approve":
        if settings.ALLOW_BOT_APPROVE and human_approved:
            return "APPROVE"
        return "COMMENT"
    return _VERDICT_TO_EVENT.get(verdict, "COMMENT")


def _finding_header(finding: dict[str, Any]) -> str:
    parts = [f"{finding['category'].upper()} - {finding['severity'].upper()}"]
    if finding.get("cwe"):
        parts.append(str(finding["cwe"]))
    if finding.get("confidence") is not None:
        parts.append(f"confidence {float(finding['confidence']):.0%}")
    return "**[" + " | ".join(parts) + "]**"


def format_finding_comment(finding: dict[str, Any]) -> str:
    body = f"{_finding_header(finding)}\n{finding['message']}"
    if finding.get("suggestion"):
        body += f"\n\n**Suggestion:**\n```\n{finding['suggestion']}\n```"
    return body


def format_review_body(summary: str | None, unplaced: list[dict[str, Any]]) -> str:
    """Summary review body, plus the findings that could not be placed on a diff line."""
    body = summary or "Review completed by GitMind."
    if unplaced:
        items = "\n".join(
            f"- `{f['file']}`{':' + str(f['line']) if f.get('line') else ''} "
            f"{_finding_header(f)} {f['message']}"
            for f in unplaced
        )
        body += f"\n\n### Findings outside the changed lines\n{items}"
    return body


def _post_to_github(
    review: dict[str, Any], findings: list[dict[str, Any]], event: str
) -> PublishResult:
    """Blocking PyGithub calls, run in a worker thread (async client: PLAN.md F4.3)."""
    gh = get_github_client()
    if gh is None:
        return PublishResult(
            posted=False,
            warning="GitHub client not configured: the review was not posted to GitHub.",
        )

    repo = gh.get_repo(review["repo"])
    pr = repo.get_pull(review["pr_number"])
    commit = (
        repo.get_commit(review["commit_id"])
        if review.get("commit_id")
        else pr.get_commits().reversed[0]
    )

    result = PublishResult(posted=False)
    unplaced: list[dict[str, Any]] = []
    for finding in findings:
        if finding.get("posted_to_github"):
            continue
        if not finding.get("line"):
            # Not on a line of the diff: reported in the summary instead
            unplaced.append(finding)
            continue
        try:
            comment = pr.create_review_comment(
                body=format_finding_comment(finding),
                commit=commit,
                path=finding["file"],
                line=int(finding["line"]),
                side="RIGHT",
            )
            result.comment_ids[finding["id"]] = str(comment.id)
            result.comments_posted += 1
        except Exception as e:
            result.comments_failed += 1
            unplaced.append(finding)
            log.warning(
                "inline_comment_failed", finding_id=finding["id"], error_type=type(e).__name__
            )

    pr.create_review(body=format_review_body(review.get("summary"), unplaced), event=event)
    result.posted = True
    return result


async def publish_review(review_id: str, *, human_approved: bool) -> PublishResult:
    """Post the review of `review_id` to its pull request."""
    review = await crud.get_review(review_id)
    if review is None:
        return PublishResult(posted=False, warning="Review not found.")
    if review["status"] == "superseded":
        return PublishResult(
            posted=False, warning="A newer commit superseded this review: not posted."
        )

    findings = await crud.get_findings(review_id)
    event = github_review_event(review.get("verdict"), human_approved)

    try:
        result = await asyncio.to_thread(_post_to_github, review, findings, event)
    except Exception as e:
        log.error("github_publish_failed", review_id=review_id, error_type=type(e).__name__)
        return PublishResult(
            posted=False,
            warning="Posting to GitHub failed. See the server logs for details.",
            retryable=True,
        )

    for finding_id, comment_id in result.comment_ids.items():
        await crud.update_finding(finding_id, posted_to_github=True, github_comment_id=comment_id)

    if result.posted and result.comments_failed:
        result.warning = (
            f"{result.comments_failed} inline comment(s) were rejected by GitHub; "
            "they are listed in the review summary instead."
        )
    log.info(
        "review_published",
        review_id=review_id,
        posted=result.posted,
        github_event=event,
        comments_posted=result.comments_posted,
        comments_failed=result.comments_failed,
    )
    return result
