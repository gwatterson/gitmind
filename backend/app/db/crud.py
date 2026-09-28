"""CRUD operations for reviews, findings, and events."""

import json
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from app.db.models import get_db

# Review statuses in which a review is still in flight
ACTIVE_STATUSES = ("pending", "running")

# SQL expression ordering severities from most to least severe
_SEVERITY_RANK_SQL = (
    "CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 "
    "WHEN 'low' THEN 3 WHEN 'info' THEN 4 ELSE 5 END"
)


def utc_now() -> str:
    """Current UTC time in the same format as SQLite CURRENT_TIMESTAMP."""
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


# Whitelists of columns that can be updated via **kwargs
_ALLOWED_REVIEW_COLUMNS = {
    "status",
    "summary",
    "verdict",
    "error",
    "completed_at",
    "llm_provider",
    "llm_model",
}
_ALLOWED_FINDING_COLUMNS = {
    "message",
    "suggestion",
    "severity",
    "posted_to_github",
    "github_comment_id",
}


# ──────────────────────────────────────────────
# Reviews
# ──────────────────────────────────────────────


async def create_review(
    repo: str,
    pr_number: int,
    pr_title: str = "",
    pr_author: str = "",
    commit_id: str = "",
) -> dict:
    """Create a new review record."""
    review_id = str(uuid.uuid4())
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO reviews (id, repo, pr_number, pr_title, pr_author, commit_id, status)
               VALUES (?, ?, ?, ?, ?, ?, 'pending')""",
            (review_id, repo, pr_number, pr_title, pr_author, commit_id),
        )
        await db.commit()
        review = await get_review(review_id)
        if review is None:
            raise RuntimeError(f"Review {review_id} not found right after insert")
        return review
    finally:
        await db.close()


async def get_review(review_id: str) -> dict | None:
    """Get a review by ID."""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM reviews WHERE id = ?", (review_id,))
        row = await cursor.fetchone()
        if row:
            return dict(row)
        return None
    finally:
        await db.close()


async def delete_review(review_id: str) -> bool:
    """Delete a review and its cascading data (findings, events)."""
    db = await get_db()
    try:
        await db.execute("DELETE FROM findings WHERE review_id = ?", (review_id,))
        await db.execute("DELETE FROM review_events WHERE review_id = ?", (review_id,))
        cursor = await db.execute("DELETE FROM reviews WHERE id = ?", (review_id,))
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()


async def list_reviews(
    limit: int = 20,
    offset: int = 0,
    status: str | None = None,
    repo: str | None = None,
) -> list[dict]:
    """List reviews with optional filters and pagination."""
    db = await get_db()
    try:
        query = "SELECT * FROM reviews"
        params: list = []
        conditions = []

        if status:
            conditions.append("status = ?")
            params.append(status)
        if repo:
            conditions.append("repo = ?")
            params.append(repo)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def update_review(review_id: str, **kwargs) -> dict | None:
    """Update review fields."""
    db = await get_db()
    try:
        fields = []
        values = []
        for key, value in kwargs.items():
            if key not in _ALLOWED_REVIEW_COLUMNS:
                raise ValueError(f"Invalid review column: {key}")
            fields.append(f"{key} = ?")
            values.append(value)
        values.append(review_id)

        if fields:
            await db.execute(
                f"UPDATE reviews SET {', '.join(fields)} WHERE id = ?",  # noqa: S608 (columns are whitelisted)
                values,
            )
            await db.commit()
        return await get_review(review_id)
    finally:
        await db.close()


async def check_duplicate_review(repo: str, commit_id: str) -> bool:
    """Check if a review is already in flight for this commit (dedup)."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id FROM reviews WHERE repo = ? AND commit_id = ? AND status IN (?, ?)",
            (repo, commit_id, *ACTIVE_STATUSES),
        )
        row = await cursor.fetchone()
        return row is not None
    finally:
        await db.close()


async def supersede_active_reviews(repo: str, pr_number: int, keep_review_id: str) -> list[str]:
    """Mark in-flight reviews of the same PR as superseded by a newer one.

    Returns the ids of the reviews that were superseded.
    """
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id FROM reviews WHERE repo = ? AND pr_number = ? AND id != ? AND status IN (?, ?)",
            (repo, pr_number, keep_review_id, *ACTIVE_STATUSES),
        )
        ids = [row["id"] for row in await cursor.fetchall()]
        for review_id in ids:
            await db.execute(
                "UPDATE reviews SET status = 'superseded', completed_at = ? WHERE id = ?",
                (utc_now(), review_id),
            )
        await db.commit()
        return ids
    finally:
        await db.close()


# ──────────────────────────────────────────────
# Findings
# ──────────────────────────────────────────────


async def create_finding(
    review_id: str,
    file: str,
    line: int,
    severity: str,
    category: str,
    message: str,
    agent: str,
    rule_id: str = "",
    suggestion: str = "",
) -> dict:
    """Create a finding record."""
    finding_id = str(uuid.uuid4())
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO findings (id, review_id, file, line, severity, category, rule_id, message, suggestion, agent)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                finding_id,
                review_id,
                file,
                line,
                severity,
                category,
                rule_id,
                message,
                suggestion,
                agent,
            ),
        )
        await db.commit()
        return {
            "id": finding_id,
            "review_id": review_id,
            "file": file,
            "line": line,
            "severity": severity,
            "category": category,
            "rule_id": rule_id,
            "message": message,
            "suggestion": suggestion,
            "agent": agent,
        }
    finally:
        await db.close()


async def create_findings_batch(
    review_id: str, findings: Sequence[Mapping[str, Any]]
) -> list[dict]:
    """Create multiple findings in a single transaction."""
    db = await get_db()
    results = []
    try:
        for f in findings:
            finding_id = str(uuid.uuid4())
            await db.execute(
                """INSERT INTO findings (id, review_id, file, line, severity, category, rule_id,
                                         message, suggestion, agent, confidence, cwe, evidence)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    finding_id,
                    review_id,
                    f["file"],
                    f.get("line", 0),
                    f["severity"],
                    f["category"],
                    f.get("rule_id", ""),
                    f["message"],
                    f.get("suggestion", ""),
                    f["agent"],
                    f.get("confidence"),
                    f.get("cwe"),
                    f.get("evidence", ""),
                ),
            )
            results.append({**f, "id": finding_id, "review_id": review_id})
        await db.commit()
        return results
    finally:
        await db.close()


async def get_findings(review_id: str) -> list[dict]:
    """Get all findings for a review."""
    db = await get_db()
    try:
        cursor = await db.execute(
            f"SELECT * FROM findings WHERE review_id = ? ORDER BY {_SEVERITY_RANK_SQL}, file, line",  # noqa: S608 (constant expression)
            (review_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def get_finding(finding_id: str) -> dict | None:
    """Get a single finding by ID."""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM findings WHERE id = ?", (finding_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def update_finding(finding_id: str, **kwargs) -> dict | None:
    """Update a finding's fields."""
    db = await get_db()
    try:
        fields = []
        values = []
        for key, value in kwargs.items():
            if key not in _ALLOWED_FINDING_COLUMNS:
                raise ValueError(f"Invalid finding column: {key}")
            fields.append(f"{key} = ?")
            values.append(value)
        values.append(finding_id)

        if fields:
            await db.execute(
                f"UPDATE findings SET {', '.join(fields)} WHERE id = ?",  # noqa: S608 (columns are whitelisted)
                values,
            )
            await db.commit()

        cursor = await db.execute("SELECT * FROM findings WHERE id = ?", (finding_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


# ──────────────────────────────────────────────
# Review Events (SSE persistence)
# ──────────────────────────────────────────────


async def create_event(
    review_id: str,
    event_type: str,
    message: str,
    data: dict | None = None,
) -> dict:
    """Create an SSE event record."""
    db = await get_db()
    try:
        data_json = json.dumps(data) if data else None
        cursor = await db.execute(
            """INSERT INTO review_events (review_id, event_type, message, data)
               VALUES (?, ?, ?, ?)""",
            (review_id, event_type, message, data_json),
        )
        await db.commit()
        return {
            "id": cursor.lastrowid,
            "review_id": review_id,
            "event_type": event_type,
            "message": message,
            "data": data,
        }
    finally:
        await db.close()


async def get_events(review_id: str, after_id: int = 0) -> list[dict]:
    """Get events for a review, optionally after a specific event ID."""
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT * FROM review_events
               WHERE review_id = ? AND id > ?
               ORDER BY id ASC""",
            (review_id, after_id),
        )
        rows = await cursor.fetchall()
        results = []
        for row in rows:
            d = dict(row)
            if d.get("data"):
                try:
                    d["data"] = json.loads(d["data"])
                except (json.JSONDecodeError, TypeError):
                    pass
            results.append(d)
        return results
    finally:
        await db.close()


# ──────────────────────────────────────────────
# Metrics / Stats
# ──────────────────────────────────────────────


async def get_review_stats() -> dict:
    """Get aggregate metrics for the dashboard."""
    db = await get_db()
    try:
        # Total reviews by status
        cursor = await db.execute("SELECT status, COUNT(*) as count FROM reviews GROUP BY status")
        status_rows = await cursor.fetchall()
        status_counts = {row["status"]: row["count"] for row in status_rows}

        # Findings by category
        cursor = await db.execute(
            "SELECT category, COUNT(*) as count FROM findings GROUP BY category"
        )
        category_rows = await cursor.fetchall()
        category_counts = {row["category"]: row["count"] for row in category_rows}

        # Findings by severity
        cursor = await db.execute(
            "SELECT severity, COUNT(*) as count FROM findings GROUP BY severity"
        )
        severity_rows = await cursor.fetchall()
        severity_counts = {row["severity"]: row["count"] for row in severity_rows}

        # Total counts
        cursor = await db.execute("SELECT COUNT(*) as total FROM reviews")
        row = await cursor.fetchone()
        total_reviews = row["total"] if row else 0

        cursor = await db.execute("SELECT COUNT(*) as total FROM findings")
        row = await cursor.fetchone()
        total_findings = row["total"] if row else 0

        return {
            "total_reviews": total_reviews,
            "total_findings": total_findings,
            "reviews_by_status": status_counts,
            "findings_by_category": category_counts,
            "findings_by_severity": severity_counts,
        }
    finally:
        await db.close()


# ──────────────────────────────────────────────
# Rate Limiter State
# ──────────────────────────────────────────────


async def get_rate_limit_state(key: str) -> str | None:
    """Get persisted rate limiter state by key."""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT value FROM rate_limit_state WHERE key = ?", (key,))
        row = await cursor.fetchone()
        return row["value"] if row else None
    finally:
        await db.close()


async def set_rate_limit_state(key: str, value: str) -> None:
    """Set persisted rate limiter state."""
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO rate_limit_state (key, value) VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP""",
            (key, value),
        )
        await db.commit()
    finally:
        await db.close()


# ──────────────────────────────────────────────
# Archive
# ──────────────────────────────────────────────


async def clear_all_reviews() -> None:
    """Clear all review data from the database."""
    db = await get_db()
    try:
        await db.execute("DELETE FROM findings")
        await db.execute("DELETE FROM review_events")
        await db.execute("DELETE FROM reviews")
        await db.commit()
    finally:
        await db.close()


# ──────────────────────────────────────────────
# Webhook deliveries (idempotency)
# ──────────────────────────────────────────────


async def record_webhook_delivery(delivery_id: str, event: str) -> bool:
    """Store a webhook delivery id. Returns False if it was already processed."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "INSERT OR IGNORE INTO webhook_deliveries (delivery_id, event) VALUES (?, ?)",
            (delivery_id, event),
        )
        await db.commit()
        return cursor.rowcount == 1
    finally:
        await db.close()


# ──────────────────────────────────────────────
# API keys
# ──────────────────────────────────────────────


async def create_api_key(
    name: str,
    prefix: str,
    key_hash: str,
    scopes: Sequence[str],
    created_by: str,
    expires_at: str | None = None,
) -> dict:
    """Store a new API key (hash only) and return its public metadata."""
    key_id = str(uuid.uuid4())
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO api_keys (id, name, prefix, key_hash, scopes, created_by, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (key_id, name, prefix, key_hash, ",".join(scopes), created_by, expires_at),
        )
        await db.commit()
    finally:
        await db.close()
    key = await get_api_key(key_id)
    if key is None:
        raise RuntimeError(f"API key {key_id} not found right after insert")
    return key


def _api_key_row(row: Any) -> dict:
    key = dict(row)
    key.pop("key_hash", None)
    key["scopes"] = [scope for scope in key["scopes"].split(",") if scope]
    return key


async def get_api_key(key_id: str) -> dict | None:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM api_keys WHERE id = ?", (key_id,))
        row = await cursor.fetchone()
        return _api_key_row(row) if row else None
    finally:
        await db.close()


async def find_active_api_key(key_hash: str) -> dict | None:
    """Return a non-revoked, non-expired key matching the hash, and record its use."""
    now = utc_now()
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT * FROM api_keys
               WHERE key_hash = ? AND revoked_at IS NULL
                 AND (expires_at IS NULL OR expires_at > ?)""",
            (key_hash, now),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        await db.execute("UPDATE api_keys SET last_used_at = ? WHERE id = ?", (now, row["id"]))
        await db.commit()
        return _api_key_row(row)
    finally:
        await db.close()


async def list_api_keys() -> list[dict]:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM api_keys ORDER BY created_at DESC")
        return [_api_key_row(row) for row in await cursor.fetchall()]
    finally:
        await db.close()


async def revoke_api_key(key_id: str) -> bool:
    db = await get_db()
    try:
        cursor = await db.execute(
            "UPDATE api_keys SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
            (utc_now(), key_id),
        )
        await db.commit()
        return cursor.rowcount == 1
    finally:
        await db.close()


# ──────────────────────────────────────────────
# Runtime settings
# ──────────────────────────────────────────────


async def get_app_setting(key: str) -> str | None:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
        row = await cursor.fetchone()
        return row["value"] if row else None
    finally:
        await db.close()


async def set_app_setting(key: str, value: str) -> None:
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO app_settings (key, value) VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP""",
            (key, value),
        )
        await db.commit()
    finally:
        await db.close()
