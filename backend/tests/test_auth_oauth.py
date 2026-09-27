"""GitHub OAuth sign-in flow (GitHub is mocked with respx)."""

from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx

from app.api.auth import GITHUB_API_URL, GITHUB_TOKEN_URL, _safe_next_path
from app.core.security import OAUTH_STATE_COOKIE, SESSION_COOKIE, decode_session_token


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("/reviews/1", "/reviews/1"),
        (None, "/"),
        ("https://evil.example", "/"),
        ("//evil.example", "/"),
        ("/\\evil.example", "/"),
        ("reviews", "/"),
    ],
)
def test_next_path_prevents_open_redirects(raw, expected):
    assert _safe_next_path(raw) == expected


async def _start_login(client: httpx.AsyncClient) -> str:
    response = await client.get("/auth/login", params={"next": "/reviews/42"})
    assert response.status_code == 302
    location = urlparse(response.headers["location"])
    assert location.netloc == "github.com"
    query = parse_qs(location.query)
    assert query["client_id"] == ["test-client-id"]
    assert query["scope"] == ["read:user read:org"]
    assert OAUTH_STATE_COOKIE in response.cookies
    client.cookies.set(OAUTH_STATE_COOKIE, response.cookies[OAUTH_STATE_COOKIE])
    return query["state"][0]


def _mock_github(login: str, orgs: list[str]) -> None:
    respx.post(GITHUB_TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "gho_test"})
    )
    respx.get(f"{GITHUB_API_URL}/user").mock(
        return_value=httpx.Response(200, json={"id": 7, "login": login, "name": "Test"})
    )
    respx.get(f"{GITHUB_API_URL}/user/orgs").mock(
        return_value=httpx.Response(200, json=[{"login": org} for org in orgs])
    )


@respx.mock
async def test_allowed_user_gets_a_session(client):
    respx.route(host="test").pass_through()
    state = await _start_login(client)
    _mock_github("alice", [])

    response = await client.get("/auth/callback", params={"code": "abc", "state": state})

    assert response.status_code == 302
    assert response.headers["location"] == "http://localhost:3000/reviews/42"
    payload = decode_session_token(response.cookies[SESSION_COOKIE])
    assert payload is not None
    assert payload["login"] == "alice"
    assert "gho_test" not in response.cookies[SESSION_COOKIE]


@respx.mock
async def test_user_not_in_allowlist_is_refused(client):
    respx.route(host="test").pass_through()
    state = await _start_login(client)
    _mock_github("mallory", ["random-org"])

    response = await client.get("/auth/callback", params={"code": "abc", "state": state})

    assert response.status_code == 302
    assert response.headers["location"].endswith("/login?error=not_allowed")
    assert SESSION_COOKIE not in response.cookies


async def test_callback_with_wrong_state_is_rejected(client):
    await _start_login(client)
    response = await client.get("/auth/callback", params={"code": "abc", "state": "forged"})
    assert response.status_code == 400


async def test_callback_without_state_cookie_is_rejected(client):
    response = await client.get("/auth/callback", params={"code": "abc", "state": "x"})
    assert response.status_code == 400


async def test_me_and_logout(user_client):
    me = await user_client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["login"] == "alice"

    logout = await user_client.post("/auth/logout")
    assert logout.status_code == 204
    assert 'gitmind_session=""' in logout.headers["set-cookie"]


async def test_status_reports_oauth_configuration(client, monkeypatch):
    from app.config import settings

    assert (await client.get("/auth/status")).json() == {
        "oauth_configured": True,
        "auth_disabled": False,
    }
    monkeypatch.setattr(settings, "GITHUB_OAUTH_CLIENT_ID", "")
    assert (await client.get("/auth/status")).json()["oauth_configured"] is False
