"""Dashboard sign-in with GitHub OAuth."""

import hmac
import secrets
from typing import Any
from urllib.parse import urlencode

import httpx
import structlog
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app.config import settings
from app.core.security import (
    OAUTH_STATE_COOKIE,
    SESSION_COOKIE,
    authenticate,
    create_session_token,
    create_state_token,
    decode_state_token,
    is_allowed,
)

router = APIRouter(prefix="/auth", tags=["auth"])
log = structlog.get_logger()

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"  # noqa: S105 (URL, not a secret)
GITHUB_API_URL = "https://api.github.com"
OAUTH_SCOPES = "read:user read:org"


def _safe_next_path(next_path: str | None) -> str:
    """Only allow relative paths on the frontend, to prevent open redirects."""
    if not next_path or not next_path.startswith("/") or next_path.startswith("//"):
        return "/"
    if "\\" in next_path or "://" in next_path:
        return "/"
    return next_path


def _frontend_url(path: str) -> str:
    return settings.FRONTEND_URL.rstrip("/") + path


def _callback_url() -> str:
    return settings.PUBLIC_API_URL.rstrip("/") + "/auth/callback"


def _set_cookie(response: Response, name: str, value: str, max_age: int, path: str = "/") -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        path=path,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
    )


@router.get("/login")
async def login(next: str | None = None) -> RedirectResponse:
    """Start the OAuth flow by redirecting the browser to GitHub."""
    next_path = _safe_next_path(next)
    if settings.AUTH_DISABLED:
        return RedirectResponse(_frontend_url(next_path), status_code=302)
    if not settings.GITHUB_OAUTH_CLIENT_ID:
        raise HTTPException(status_code=503, detail="GitHub OAuth is not configured")

    state = secrets.token_urlsafe(32)
    query = urlencode(
        {
            "client_id": settings.GITHUB_OAUTH_CLIENT_ID,
            "redirect_uri": _callback_url(),
            "scope": OAUTH_SCOPES,
            "state": state,
            "allow_signup": "false",
        }
    )
    response = RedirectResponse(f"{GITHUB_AUTHORIZE_URL}?{query}", status_code=302)
    _set_cookie(response, OAUTH_STATE_COOKIE, create_state_token(state, next_path), 600, "/auth")
    return response


async def _fetch_github_identity(code: str) -> tuple[dict[str, Any], list[str]]:
    """Exchange the OAuth code and read the user profile and organizations.

    The GitHub access token is used only here and never stored.
    """
    async with httpx.AsyncClient(timeout=10) as client:
        token_response = await client.post(
            GITHUB_TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.GITHUB_OAUTH_CLIENT_ID,
                "client_secret": settings.GITHUB_OAUTH_CLIENT_SECRET.get_secret_value(),
                "code": code,
                "redirect_uri": _callback_url(),
            },
        )
        token_response.raise_for_status()
        access_token = token_response.json().get("access_token")
        if not access_token:
            raise ValueError("GitHub did not return an access token")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
        }
        user_response = await client.get(f"{GITHUB_API_URL}/user", headers=headers)
        user_response.raise_for_status()
        orgs_response = await client.get(
            f"{GITHUB_API_URL}/user/orgs", headers=headers, params={"per_page": 100}
        )
        orgs_response.raise_for_status()

    user: dict[str, Any] = user_response.json()
    orgs = [org["login"] for org in orgs_response.json()]
    return user, orgs


@router.get("/callback")
async def callback(
    request: Request, code: str | None = None, state: str | None = None
) -> RedirectResponse:
    """Complete the OAuth flow and create the session cookie."""
    state_cookie = request.cookies.get(OAUTH_STATE_COOKIE)
    stored = decode_state_token(state_cookie) if state_cookie else None
    if not code or not state or not stored or not hmac.compare_digest(stored["state"], state):
        raise HTTPException(status_code=400, detail="Invalid or expired sign-in attempt")

    try:
        user, orgs = await _fetch_github_identity(code)
    except (httpx.HTTPError, ValueError) as e:
        log.warning("oauth_exchange_failed", error_type=type(e).__name__)
        return RedirectResponse(_frontend_url("/login?error=github"), status_code=302)

    if not is_allowed(user["login"], orgs):
        log.warning("oauth_user_not_allowed", login=user["login"])
        response = RedirectResponse(_frontend_url("/login?error=not_allowed"), status_code=302)
        response.delete_cookie(OAUTH_STATE_COOKIE, path="/auth")
        return response

    log.info("user_signed_in", login=user["login"])
    response = RedirectResponse(_frontend_url(stored.get("next", "/")), status_code=302)
    _set_cookie(
        response,
        SESSION_COOKIE,
        create_session_token(user, orgs),
        settings.SESSION_TTL_HOURS * 3600,
    )
    response.delete_cookie(OAUTH_STATE_COOKIE, path="/auth")
    return response


@router.get("/status")
async def auth_status() -> dict[str, bool]:
    """Public: tells the sign-in page whether GitHub OAuth is set up."""
    return {
        "oauth_configured": bool(
            settings.GITHUB_OAUTH_CLIENT_ID
            and settings.GITHUB_OAUTH_CLIENT_SECRET.get_secret_value()
        ),
        "auth_disabled": settings.AUTH_DISABLED,
    }


@router.get("/me")
async def me(request: Request) -> dict[str, Any]:
    """Return the signed-in user, or 401."""
    principal = await authenticate(request)
    if principal is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return {"user": principal.public_dict(), "auth_disabled": settings.AUTH_DISABLED}


@router.post("/logout")
async def logout() -> Response:
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response
