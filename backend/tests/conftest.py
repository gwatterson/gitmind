"""Shared test configuration.

Tests must never touch the developer's real database or call external services,
so the environment is overridden before any `app` module is imported.
"""

import os
import tempfile
from pathlib import Path

# Environment variables take precedence over values read from backend/.env
_SESSION_DIR = Path(tempfile.mkdtemp(prefix="gitmind-tests-"))
os.environ["DATABASE_PATH"] = str(_SESSION_DIR / "session.db")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_SESSION_DIR / 'session.db'}"
os.environ["GEMINI_API_KEY"] = "test-key"
os.environ["GITHUB_TOKEN"] = ""
os.environ["GITHUB_APP_ID"] = ""
os.environ["GITHUB_PRIVATE_KEY_PATH"] = ""
os.environ["GITHUB_WEBHOOK_SECRET"] = "test-webhook-secret"
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["HITL_ENABLED"] = "false"

import pytest  # noqa: E402

from app.db import models  # noqa: E402


@pytest.fixture(autouse=True)
async def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Give every test its own empty, initialized SQLite database."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(models, "DATABASE_PATH", str(db_path))
    await models.init_db()
    return db_path
