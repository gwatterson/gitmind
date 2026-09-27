"""Authentication and authorization.

Two ways to authenticate:
- Dashboard users: GitHub OAuth, then a signed session cookie (JWT, HttpOnly).
- Automation: API keys sent as "Authorization: Bearer gm_...", stored as SHA-256 hashes.

Cookie-authenticated requests that change state must also send the header
"X-Requested-With: gitmind". Browsers do not let other sites set custom headers
on cross-site requests without a CORS preflight, which blocks CSRF.
"""

import hashlib
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

import jwt
import structlog
from fastapi import HTTPException, Request

from app.config import settings
from app.db import crud

log = structlog.get_logger()

SCOPE_READ = "reviews:read"
SCOPE_WRITE = "reviews:write"
ALL_SCOPES = frozenset({SCOPE_READ, SCOPE_WRITE})

SESSION_COOKIE = "gitmind_session"
OAUTH_STATE_COOKIE = "gitmind_oauth_state"
CSRF_HEADER = "X-Requested-With"
CSRF_HEADER_VALUE = "gitmind"
API_KEY_PREFIX = "gm_"

_JWT_ALGORITHM = "HS256"
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@dataclass(frozen=True)
class Principal:
    """The authenticated caller of a request."""

    kind: Literal["user", "api_key", "dev"]
    login: str
    scopes: frozenset[str]
    is_admin: bool = False
    name: str | None = None
    avatar_url: str | None = None
    orgs: tuple[str, ...] = field(default_factory=tuple)

    def public_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "login": self.login,
            "name": self.name,
            "avatar_url": self.avatar_url,
            "is_admin": self.is_admin,
            "scopes": sorted(self.scopes),
        }


DEV_PRINCIPAL = Principal(kind="dev", login="local-dev", scopes=ALL_SCOPES, is_admin=True)


# ──────────────────────────────────────────────
# Allowlist
# ──────────────────────────────────────────────


def is_allowed(login: str, orgs: list[str] | tuple[str, ...]) -> bool:
    """A user may sign in if listed by login or member of an allowed organization."""
    if login.lower() in settings.allowed_users:
        return True
    return any(org.lower() in settings.allowed_orgs for org in orgs)


def is_admin(login: str) -> bool:
    return login.lower() in settings.admin_users


# ──────────────────────────────────────────────
# Session tokens
# ──────────────────────────────────────────────


def create_session_token(user: dict[str, Any], orgs: list[str]) -> str:
    now = int(time.time())
    payload = {
        "typ": "session",
        "sub": str(user["id"]),
        "login": user["login"],
        "name": user.get("name"),
        "avatar_url": user.get("avatar_url"),
        "orgs": orgs,
        "iat": now,
        "exp": now + settings.SESSION_TTL_HOURS * 3600,
    }
    return jwt.encode(payload, settings.SESSION_SECRET.get_secret_value(), _JWT_ALGORITHM)


def decode_session_token(token: str) -> dict[str, Any] | None:
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.SESSION_SECRET.get_secret_value(),
            algorithms=[_JWT_ALGORITHM],
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError:
        return None
    if payload.get("typ") != "session":
        return None
    return payload


def create_state_token(state: str, next_path: str) -> str:
    """Short-lived signed token binding the OAuth state to the browser."""
    now = int(time.time())
    payload = {"typ": "oauth_state", "state": state, "next": next_path, "exp": now + 600}
    return jwt.encode(payload, settings.SESSION_SECRET.get_secret_value(), _JWT_ALGORITHM)


def decode_state_token(token: str) -> dict[str, Any] | None:
    try:
        payload: dict[str, Any] = jwt.decode(
            token, settings.SESSION_SECRET.get_secret_value(), algorithms=[_JWT_ALGORITHM]
        )
    except jwt.PyJWTError:
        return None
    return payload if payload.get("typ") == "oauth_state" else None


# ──────────────────────────────────────────────
# API keys
# ──────────────────────────────────────────────


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    """Return (plaintext key, display prefix, hash). The plaintext is shown only once."""
    key = API_KEY_PREFIX + secrets.token_urlsafe(32)
    return key, key[:10], hash_api_key(key)


# ──────────────────────────────────────────────
# Request authentication
# ──────────────────────────────────────────────


def _principal_from_session(payload: dict[str, Any]) -> Principal | None:
    login = payload.get("login", "")
    orgs = tuple(payload.get("orgs") or ())
    # The allowlist is re-checked on every request, so removing a user takes effect
    # immediately instead of when the session expires.
    if not login or not is_allowed(login, orgs):
        return None
    return Principal(
        kind="user",
        login=login,
        scopes=ALL_SCOPES,
        is_admin=is_admin(login),
        name=payload.get("name"),
        avatar_url=payload.get("avatar_url"),
        orgs=orgs,
    )


async def authenticate(request: Request) -> Principal | None:
    """Identify the caller, or return None if the request is anonymous."""
    if settings.AUTH_DISABLED:
        return DEV_PRINCIPAL

    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        if not token.startswith(API_KEY_PREFIX):
            return None
        key = await crud.find_active_api_key(hash_api_key(token))
        if key is None:
            return None
        return Principal(
            kind="api_key",
            login=f"api-key:{key['name']}",
            scopes=frozenset(key["scopes"]),
        )

    session = request.cookies.get(SESSION_COOKIE)
    if session:
        payload = decode_session_token(session)
        if payload:
            return _principal_from_session(payload)
    return None


def _check_csrf(request: Request, principal: Principal) -> None:
    if principal.kind != "user" or request.method in _SAFE_METHODS:
        return
    if request.headers.get(CSRF_HEADER) != CSRF_HEADER_VALUE:
        raise HTTPException(status_code=403, detail=f"Missing {CSRF_HEADER} header")


def require_scope(scope: str) -> Callable[[Request], Awaitable[Principal]]:
    """FastAPI dependency factory: the caller must be authenticated and hold `scope`."""

    async def dependency(request: Request) -> Principal:
        principal = await authenticate(request)
        if principal is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        if scope not in principal.scopes:
            raise HTTPException(status_code=403, detail=f"Missing scope: {scope}")
        _check_csrf(request, principal)
        request.state.principal = principal
        return principal

    return dependency


async def require_admin(request: Request) -> Principal:
    """FastAPI dependency: the caller must be a signed-in administrator."""
    principal = await require_scope(SCOPE_WRITE)(request)
    if not principal.is_admin:
        raise HTTPException(status_code=403, detail="Administrator rights required")
    return principal


require_read = require_scope(SCOPE_READ)
require_write = require_scope(SCOPE_WRITE)
