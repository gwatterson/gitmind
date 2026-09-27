"""Database helpers, data migrations and log secret masking."""

import re

from app.core.logging import REDACTED, mask_secrets
from app.db import crud, models


def test_utc_now_matches_sqlite_timestamp_format():
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", crud.utc_now())


async def test_startup_migration_clears_literal_completed_at():
    review = await crud.create_review(repo="o/r", pr_number=1)
    db = await models.get_db()
    try:
        await db.execute(
            "UPDATE reviews SET completed_at = ? WHERE id = ?", ("datetime('now')", review["id"])
        )
        await db.commit()
    finally:
        await db.close()

    await models.init_db()

    stored = await crud.get_review(review["id"])
    assert stored is not None and stored["completed_at"] is None


async def test_webhook_delivery_is_recorded_once():
    assert await crud.record_webhook_delivery("abc", "pull_request") is True
    assert await crud.record_webhook_delivery("abc", "pull_request") is False


async def test_supersede_only_touches_active_reviews_of_the_same_pr():
    old = await crud.create_review(repo="o/r", pr_number=1, commit_id="a")
    done = await crud.create_review(repo="o/r", pr_number=1, commit_id="b")
    await crud.update_review(done["id"], status="completed")
    other_pr = await crud.create_review(repo="o/r", pr_number=2, commit_id="c")
    new = await crud.create_review(repo="o/r", pr_number=1, commit_id="d")

    superseded = await crud.supersede_active_reviews("o/r", 1, new["id"])

    assert superseded == [old["id"]]
    statuses = {r["id"]: r["status"] for r in await crud.list_reviews(limit=10)}
    assert statuses[done["id"]] == "completed"
    assert statuses[other_pr["id"]] == "pending"
    assert statuses[new["id"]] == "pending"


def test_sensitive_keys_are_redacted():
    event = mask_secrets(
        None,
        "info",
        {"event": "x", "token": "abc", "Authorization": "Bearer abc", "nested": {"api_key": "k"}},
    )
    assert event["token"] == REDACTED
    assert event["Authorization"] == REDACTED
    assert event["nested"]["api_key"] == REDACTED


def test_credentials_inside_free_text_are_redacted():
    event = mask_secrets(
        None,
        "error",
        {
            "event": "failed",
            "error": "Bad credentials for ghp_abcdefghijklmnopqrstuvwxyz0123 and "  # gitleaks:allow (fake token)
            "AIzaSyA1234567890abcdefghijklmnopqrstuv",  # gitleaks:allow (fake key)
        },
    )
    assert "ghp_" not in event["error"]
    assert "AIza" not in event["error"]
    assert event["error"].count(REDACTED) == 2
