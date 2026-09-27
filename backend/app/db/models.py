"""SQLite database models and initialization using aiosqlite."""

import aiosqlite

from app.config import settings

DATABASE_PATH = settings.DATABASE_PATH

SCHEMA_SQL = """
-- Main reviews table
CREATE TABLE IF NOT EXISTS reviews (
    id TEXT PRIMARY KEY,
    repo TEXT NOT NULL,
    pr_number INTEGER NOT NULL,
    pr_title TEXT,
    pr_author TEXT,
    commit_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    verdict TEXT,
    summary TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME,
    error TEXT
);

-- Findings table
CREATE TABLE IF NOT EXISTS findings (
    id TEXT PRIMARY KEY,
    review_id TEXT REFERENCES reviews(id),
    file TEXT NOT NULL,
    line INTEGER,
    severity TEXT NOT NULL,
    category TEXT NOT NULL,
    rule_id TEXT,
    message TEXT NOT NULL,
    suggestion TEXT,
    agent TEXT NOT NULL,
    posted_to_github BOOLEAN DEFAULT FALSE,
    github_comment_id TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- SSE events (for replay and persistence)
CREATE TABLE IF NOT EXISTS review_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id TEXT REFERENCES reviews(id),
    event_type TEXT NOT NULL,
    message TEXT,
    data TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Rate limiter counters (persist RPD across restarts)
CREATE TABLE IF NOT EXISTS rate_limit_state (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Processed GitHub webhook deliveries (idempotency on X-GitHub-Delivery)
CREATE TABLE IF NOT EXISTS webhook_deliveries (
    delivery_id TEXT PRIMARY KEY,
    event TEXT NOT NULL,
    received_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- API keys for machine-to-machine access (only the SHA-256 hash is stored)
CREATE TABLE IF NOT EXISTS api_keys (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    prefix TEXT NOT NULL,
    key_hash TEXT NOT NULL UNIQUE,
    scopes TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME,
    last_used_at DATETIME,
    revoked_at DATETIME
);

-- Index for faster lookups
CREATE INDEX IF NOT EXISTS idx_findings_review_id ON findings(review_id);
CREATE INDEX IF NOT EXISTS idx_review_events_review_id ON review_events(review_id);
CREATE INDEX IF NOT EXISTS idx_reviews_status ON reviews(status);
CREATE INDEX IF NOT EXISTS idx_reviews_repo ON reviews(repo);
CREATE INDEX IF NOT EXISTS idx_reviews_repo_pr ON reviews(repo, pr_number);
"""


async def get_db() -> aiosqlite.Connection:
    """Get a database connection."""
    db = await aiosqlite.connect(DATABASE_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


# Idempotent data fixes applied at startup (a real migration tool arrives with PLAN.md F4.2)
DATA_MIGRATIONS = [
    # completed_at used to be stored as the literal text "datetime('now')"
    "UPDATE reviews SET completed_at = NULL WHERE completed_at LIKE 'datetime(%'",
]


async def init_db() -> None:
    """Initialize the database schema and apply pending data fixes."""
    db = await get_db()
    try:
        await db.executescript(SCHEMA_SQL)
        for statement in DATA_MIGRATIONS:
            await db.execute(statement)
        await db.commit()
    finally:
        await db.close()
