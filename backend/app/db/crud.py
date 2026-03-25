"""CRUD operations for reviews, findings, and events."""

import json
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

import aiosqlite

from app.db.models import get_db


# Whitelists of columns that can be updated via **kwargs
_ALLOWED_REVIEW_COLUMNS = {"status", "summary", "verdict", "error", "completed_at"}
_ALLOWED_FINDING_COLUMNS = {"message", "suggestion", "severity", "posted_to_github", "github_comment_id"}


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
        return await get_review(review_id)
    finally:
        await db.close()


async def get_review(review_id: str) -> Optional[dict]:
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
    status: Optional[str] = None,
    repo: Optional[str] = None,
) -> List[dict]:
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


async def update_review(review_id: str, **kwargs) -> Optional[dict]:
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
                f"UPDATE reviews SET {', '.join(fields)} WHERE id = ?",
                values,
            )
            await db.commit()
        return await get_review(review_id)
    finally:
        await db.close()


async def check_duplicate_review(repo: str, commit_id: str) -> bool:
    """Check if a review already exists for this commit (dedup)."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id FROM reviews WHERE repo = ? AND commit_id = ? AND status IN ('pending', 'running')",
            (repo, commit_id),
        )
        row = await cursor.fetchone()
        return row is not None
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
            (finding_id, review_id, file, line, severity, category, rule_id, message, suggestion, agent),
        )
        await db.commit()
        return {
            "id": finding_id, "review_id": review_id, "file": file, "line": line,
            "severity": severity, "category": category, "rule_id": rule_id,
            "message": message, "suggestion": suggestion, "agent": agent,
        }
    finally:
        await db.close()


async def create_findings_batch(review_id: str, findings: List[dict]) -> List[dict]:
    """Create multiple findings in a single transaction."""
    db = await get_db()
    results = []
    try:
        for f in findings:
            finding_id = str(uuid.uuid4())
            await db.execute(
                """INSERT INTO findings (id, review_id, file, line, severity, category, rule_id, message, suggestion, agent)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (finding_id, review_id, f["file"], f.get("line", 0), f["severity"],
                 f["category"], f.get("rule_id", ""), f["message"], f.get("suggestion", ""), f["agent"]),
            )
            results.append({**f, "id": finding_id, "review_id": review_id})
        await db.commit()
        return results
    finally:
        await db.close()


async def get_findings(review_id: str) -> List[dict]:
    """Get all findings for a review."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM findings WHERE review_id = ? ORDER BY severity, file, line",
            (review_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def update_finding(finding_id: str, **kwargs) -> Optional[dict]:
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
                f"UPDATE findings SET {', '.join(fields)} WHERE id = ?",
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
    data: Optional[dict] = None,
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


async def get_events(review_id: str, after_id: int = 0) -> List[dict]:
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
        cursor = await db.execute(
            "SELECT status, COUNT(*) as count FROM reviews GROUP BY status"
        )
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
        total_reviews = (await cursor.fetchone())["total"]

        cursor = await db.execute("SELECT COUNT(*) as total FROM findings")
        total_findings = (await cursor.fetchone())["total"]

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

async def get_rate_limit_state(key: str) -> Optional[str]:
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
            (key, value)
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
