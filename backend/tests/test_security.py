"""Authentication, authorization, CSRF, API keys and secure configuration."""

import time

import jwt
import pytest
from pydantic import ValidationError

from app.config import Settings, settings
from app.core.security import (
    CSRF_HEADER,
    SESSION_COOKIE,
    decode_session_token,
    generate_api_key,
    hash_api_key,
)
from app.db import crud
from tests.conftest import session_token

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────


def _production(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "ENVIRONMENT": "production",
        "AUTH_DISABLED": False,
        "GITHUB_WEBHOOK_SECRET": "whsec",
        "SESSION_SECRET": "x" * 40,
        "GITHUB_OAUTH_CLIENT_ID": "id",
        "GITHUB_OAUTH_CLIENT_SECRET": "secret",
        "AUTH_ALLOWED_USERS": "alice",
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def test_secure_production_config_is_accepted():
    assert _production().is_production


@pytest.mark.parametrize(
    "overrides",
    [
        {"AUTH_DISABLED": True},
        {"GITHUB_WEBHOOK_SECRET": ""},
        {"SESSION_SECRET": "too-short"},
        {"GITHUB_OAUTH_CLIENT_SECRET": ""},
        {"AUTH_ALLOWED_USERS": "", "AUTH_ALLOWED_ORGS": ""},
    ],
)
def test_insecure_production_config_is_rejected(overrides):
    with pytest.raises(ValidationError, match="Insecure production configuration"):
        _production(**overrides)


def test_development_generates_a_session_secret_when_missing():
    dev = Settings(ENVIRONMENT="development", SESSION_SECRET="")  # type: ignore[arg-type]
    assert len(dev.SESSION_SECRET.get_secret_value()) >= 32


# ──────────────────────────────────────────────
# Sessions
# ──────────────────────────────────────────────


def test_session_token_roundtrip():
    payload = decode_session_token(session_token("alice"))
    assert payload is not None
    assert payload["login"] == "alice"


def test_tampered_or_expired_session_is_rejected():
    secret = settings.SESSION_SECRET.get_secret_value()
    forged = jwt.encode({"typ": "session", "sub": "1", "login": "alice"}, "w" * 48, "HS256")
    expired = jwt.encode(
        {"typ": "session", "sub": "1", "login": "alice", "iat": 0, "exp": int(time.time()) - 10},
        secret,
        "HS256",
    )
    assert decode_session_token(forged) is None
    assert decode_session_token(expired) is None


async def test_protected_endpoints_require_authentication(client):
    for method, path in [
        ("GET", "/api/reviews"),
        ("GET", "/api/stats"),
        ("GET", "/api/rate-limit/status"),
        ("POST", "/api/reviews/trigger"),
        ("DELETE", "/api/reviews"),
        ("GET", "/api/keys"),
    ]:
        response = await client.request(method, path)
        assert response.status_code == 401, f"{method} {path}"


async def test_health_is_public_and_leaks_nothing(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_signed_in_user_can_read(user_client):
    response = await user_client.get("/api/reviews")
    assert response.status_code == 200


async def test_user_removed_from_allowlist_loses_access(client, monkeypatch):
    client.cookies.set(SESSION_COOKIE, session_token("alice"))
    monkeypatch.setattr(settings, "AUTH_ALLOWED_USERS", "someone-else")
    response = await client.get("/api/reviews")
    assert response.status_code == 401


async def test_org_membership_grants_access(client):
    client.cookies.set(SESSION_COOKIE, session_token("bob", orgs=["Trusted-Org"]))
    response = await client.get("/api/reviews")
    assert response.status_code == 200


async def test_state_changing_request_without_csrf_header_is_rejected(user_client):
    del user_client.headers[CSRF_HEADER]
    response = await user_client.delete("/api/reviews/some-id")
    assert response.status_code == 403
    assert CSRF_HEADER in response.json()["detail"]


async def test_clear_archive_requires_admin(user_client):
    response = await user_client.delete("/api/reviews")
    assert response.status_code == 403


async def test_admin_can_clear_archive(admin_client):
    response = await admin_client.delete("/api/reviews")
    assert response.status_code == 200


async def test_auth_disabled_grants_dev_admin(client, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_DISABLED", True)
    me = await client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["is_admin"] is True
    assert me.json()["auth_disabled"] is True


# ──────────────────────────────────────────────
# API keys
# ──────────────────────────────────────────────


def test_generated_api_keys_are_hashed():
    plaintext, prefix, key_hash = generate_api_key()
    assert plaintext.startswith("gm_")
    assert plaintext.startswith(prefix)
    assert key_hash == hash_api_key(plaintext)
    assert plaintext not in key_hash


async def test_api_key_lifecycle(admin_client, client):
    created = await admin_client.post(
        "/api/keys", json={"name": "ci", "scopes": ["reviews:read"], "expires_in_days": 30}
    )
    assert created.status_code == 201
    key = created.json()["key"]
    key_id = created.json()["api_key"]["id"]
    assert "key_hash" not in created.json()["api_key"]

    headers = {"Authorization": f"Bearer {key}"}
    assert (await client.get("/api/reviews", headers=headers)).status_code == 200
    # read-only key cannot write, and API keys do not need the CSRF header
    denied = await client.post(
        "/api/reviews/trigger", json={"repo": "o/r", "pr_number": 1}, headers=headers
    )
    assert denied.status_code == 403
    assert "reviews:write" in denied.json()["detail"]

    assert (await admin_client.delete(f"/api/keys/{key_id}")).status_code == 200
    assert (await client.get("/api/reviews", headers=headers)).status_code == 401


async def test_expired_api_key_is_rejected(client):
    plaintext, prefix, key_hash = generate_api_key()
    await crud.create_api_key(
        name="old",
        prefix=prefix,
        key_hash=key_hash,
        scopes=["reviews:read"],
        created_by="root",
        expires_at="2000-01-01 00:00:00",
    )
    response = await client.get("/api/reviews", headers={"Authorization": f"Bearer {plaintext}"})
    assert response.status_code == 401


async def test_non_admin_cannot_manage_api_keys(user_client):
    response = await user_client.post("/api/keys", json={"name": "x"})
    assert response.status_code == 403


async def test_invalid_scope_is_rejected(admin_client):
    response = await admin_client.post("/api/keys", json={"name": "x", "scopes": ["admin:all"]})
    assert response.status_code == 422
