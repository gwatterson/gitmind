"""Shared test configuration.

Tests must never touch the developer's real database or call external services,
so the environment is overridden before any `app` module is imported.
"""

import os
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

# Environment variables take precedence over values read from backend/.env
_SESSION_DIR = Path(tempfile.mkdtemp(prefix="gitmind-tests-"))
os.environ.update(
    {
        "ENVIRONMENT": "development",
        "DATABASE_PATH": str(_SESSION_DIR / "session.db"),
        "DATABASE_URL": f"sqlite+aiosqlite:///{_SESSION_DIR / 'session.db'}",
        "GEMINI_API_KEY": "test-key",
        "GITHUB_TOKEN": "",
        "GITHUB_APP_ID": "",
        "GITHUB_PRIVATE_KEY_PATH": "",
        "GITHUB_WEBHOOK_SECRET": "test-webhook-secret",
        "GITHUB_OAUTH_CLIENT_ID": "test-client-id",
        "GITHUB_OAUTH_CLIENT_SECRET": "test-client-secret",
        "AUTH_DISABLED": "false",
        "AUTH_ALLOWED_USERS": "alice,root",
        "AUTH_ALLOWED_ORGS": "trusted-org",
        "AUTH_ADMIN_USERS": "root",
        "SESSION_SECRET": "test-session-secret-that-is-long-enough-1234567890",
        "LANGSMITH_TRACING": "false",
        "HITL_ENABLED": "false",
        "ALLOW_BOT_APPROVE": "false",
        "LLM_PROVIDER": "gemini",
        "LLM_RETRY_WAIT_SECONDS": "0",
        "OLLAMA_BASE_URL": "http://ollama.test:11434",
        # Pipeline tests script the agents' answers; the verifier has its own tests
        "VERIFIER_ENABLED": "false",
    }
)

import httpx  # noqa: E402
import pytest  # noqa: E402

from app.core.ratelimit import limiter  # noqa: E402
from app.core.security import CSRF_HEADER, CSRF_HEADER_VALUE, SESSION_COOKIE  # noqa: E402
from app.core.security import create_session_token as _create_session_token  # noqa: E402
from app.db import models  # noqa: E402
from app.llm import factory  # noqa: E402


@pytest.fixture(autouse=True)
async def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Give every test its own empty, initialized SQLite database."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(models, "DATABASE_PATH", str(db_path))
    await models.init_db()
    return db_path


@pytest.fixture(autouse=True)
def reset_http_rate_limits() -> None:
    limiter.reset()


@pytest.fixture(autouse=True)
def reset_llm_provider() -> None:
    """Every test starts with the provider from the environment."""
    factory.reset_runtime_provider()


def session_token(login: str = "alice", orgs: list[str] | None = None) -> str:
    return _create_session_token(
        {"id": 1, "login": login, "name": login.title(), "avatar_url": None}, orgs or []
    )


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """Anonymous HTTP client bound to the ASGI app (no network)."""
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _signed_in(c: httpx.AsyncClient, login: str) -> httpx.AsyncClient:
    c.cookies.set(SESSION_COOKIE, session_token(login))
    c.headers[CSRF_HEADER] = CSRF_HEADER_VALUE
    return c


@pytest.fixture
async def user_client(client: httpx.AsyncClient) -> httpx.AsyncClient:
    """Client signed in as a regular allowlisted user."""
    return _signed_in(client, "alice")


@pytest.fixture
async def admin_client(client: httpx.AsyncClient) -> httpx.AsyncClient:
    """Client signed in as an administrator."""
    return _signed_in(client, "root")
