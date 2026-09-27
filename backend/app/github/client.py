"""Authenticated PyGithub client (GitHub App installation token or personal token)."""

import structlog
from github import Auth, Github, GithubIntegration

from app.config import settings

log = structlog.get_logger()


def get_github_client() -> Github | None:
    """Return an authenticated GitHub client, or None if no credentials are configured.

    GitHub App credentials take precedence; a personal access token is the
    development fallback.
    """
    if settings.GITHUB_APP_ID and settings.GITHUB_PRIVATE_KEY_PATH:
        try:
            with open(settings.GITHUB_PRIVATE_KEY_PATH) as key_file:
                private_key = key_file.read()
            integration = GithubIntegration(
                auth=Auth.AppAuth(int(settings.GITHUB_APP_ID), private_key)
            )
            # Single-installation setup for now: multi-installation support is PLAN.md F4.6
            installations = list(integration.get_installations())
            if installations:
                return installations[0].get_github_for_installation()
            log.warning("github_app_has_no_installations")
        except Exception as e:
            log.error("github_app_auth_failed", error_type=type(e).__name__)

    token = settings.GITHUB_TOKEN.get_secret_value()
    if token:
        return Github(auth=Auth.Token(token))

    log.warning("github_client_not_configured")
    return None
