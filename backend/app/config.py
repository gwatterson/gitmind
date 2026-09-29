"""Application settings via pydantic-settings. All values from environment variables."""

import secrets
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings

MIN_SESSION_SECRET_LENGTH = 32


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings(BaseSettings):
    # Runtime environment: "production" enforces a secure configuration at startup
    ENVIRONMENT: Literal["development", "production"] = "development"

    # Gemini LLM
    GEMINI_API_KEY: SecretStr = SecretStr("")
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # LLM provider: "gemini" (Google API) or "ollama" (local model, no quota)
    LLM_PROVIDER: Literal["gemini", "ollama"] = "gemini"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5-coder:7b"
    OLLAMA_NUM_CTX: int = 16384  # context window requested from Ollama (its default is small)

    # LLM calls
    LLM_TIMEOUT_SECONDS: float = 180.0
    LLM_MAX_ATTEMPTS: int = 3  # transient errors and invalid structured output are retried
    LLM_RETRY_WAIT_SECONDS: float = 2.0  # base of the exponential backoff
    LLM_MAX_CONCURRENCY: int = 3  # parallel LLM calls per agent
    LLM_INPUT_TOKEN_BUDGET: int = 24_000  # max estimated tokens of diff per agent call

    # LLM rate limiter (Tier 1 with 20% safety margin)
    RATE_LIMIT_RPM_MAX: int = 120  # 80% of 150 RPM
    RATE_LIMIT_RPD_MAX: int = 1200  # 80% of 1500 RPD
    RATE_LIMIT_TPM_MAX: int = 800_000  # 80% of 1M TPM

    # GitHub App
    GITHUB_APP_ID: str = ""
    GITHUB_PRIVATE_KEY_PATH: str = ""
    GITHUB_WEBHOOK_SECRET: SecretStr = SecretStr("")
    GITHUB_TOKEN: SecretStr = SecretStr("")
    WEBHOOK_MAX_BODY_BYTES: int = 25 * 1024 * 1024  # GitHub caps payloads at 25 MB

    # Dashboard authentication (GitHub OAuth App)
    AUTH_DISABLED: bool = False  # local development only, refused in production
    GITHUB_OAUTH_CLIENT_ID: str = ""
    GITHUB_OAUTH_CLIENT_SECRET: SecretStr = SecretStr("")
    AUTH_ALLOWED_USERS: str = ""  # comma-separated GitHub logins
    AUTH_ALLOWED_ORGS: str = ""  # comma-separated GitHub organizations
    AUTH_ADMIN_USERS: str = ""  # comma-separated GitHub logins with admin rights
    SESSION_SECRET: SecretStr = SecretStr("")
    SESSION_TTL_HOURS: int = 24 * 7

    # Public URLs (used for OAuth redirects and cookies)
    PUBLIC_API_URL: str = "http://localhost:8000"
    FRONTEND_URL: str = "http://localhost:3000"

    # HTTP rate limiting (per user or per IP)
    HTTP_RATE_LIMIT_ENABLED: bool = True
    HTTP_RATE_LIMIT_DEFAULT: str = "120/minute"
    HTTP_RATE_LIMIT_TRIGGER: str = "10/hour"

    # LangSmith (optional)
    LANGSMITH_API_KEY: SecretStr = SecretStr("")
    LANGSMITH_TRACING: bool = False
    LANGCHAIN_PROJECT: str = "code-review-agent"

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./reviews.db"
    DATABASE_PATH: str = "./reviews.db"

    # Review behavior
    HITL_ENABLED: bool = False
    REVIEW_DRAFT_PRS: bool = False
    # The bot never approves a PR on its own: "approve" verdicts are posted as
    # comments unless this is enabled AND a human approved the review (HITL).
    ALLOW_BOT_APPROVE: bool = False

    # Review scope: bigger pull requests are reviewed partially, and the summary says so
    MAX_REVIEW_FILES: int = 100
    MAX_REVIEW_PATCH_CHARS: int = 400_000
    REVIEW_EXCLUDE_PATTERNS: str = ""  # extra comma-separated globs, e.g. "docs/*,*.md"

    # Verifier node: a second LLM pass that suppresses findings the code does not support.
    # Findings below the threshold are stored as suppressed and never published.
    VERIFIER_ENABLED: bool = True
    VERIFIER_MIN_CONFIDENCE: float = 0.5

    # Which findings can make the verdict "request_changes": critical or high findings of
    # these categories, with at least this self-reported confidence. The evaluation showed
    # that quality and performance findings are mostly noise and that the confidence the
    # model reports does not separate real problems from false alarms (see eval/README.md).
    VERDICT_BLOCKING_CATEGORIES: str = "security"
    VERDICT_MIN_CONFIDENCE: float = 0.0

    # Directory of the prompt files; empty means the versioned prompts in app/graph/prompts
    PROMPTS_DIR: str = ""

    # App
    CORS_ORIGINS: str = "http://localhost:3000"
    LOG_LEVEL: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def verdict_blocking_categories(self) -> set[str]:
        return set(_split_csv(self.VERDICT_BLOCKING_CATEGORIES))

    @property
    def review_exclude_patterns(self) -> list[str]:
        return _split_csv(self.REVIEW_EXCLUDE_PATTERNS)

    @property
    def cors_origins_list(self) -> list[str]:
        return _split_csv(self.CORS_ORIGINS)

    @property
    def allowed_users(self) -> set[str]:
        return {login.lower() for login in _split_csv(self.AUTH_ALLOWED_USERS)}

    @property
    def allowed_orgs(self) -> set[str]:
        return {org.lower() for org in _split_csv(self.AUTH_ALLOWED_ORGS)}

    @property
    def admin_users(self) -> set[str]:
        return {login.lower() for login in _split_csv(self.AUTH_ADMIN_USERS)}

    @model_validator(mode="after")
    def _check_security(self) -> "Settings":
        if self.is_production:
            problems = []
            if self.AUTH_DISABLED:
                problems.append("AUTH_DISABLED must be false")
            if not self.GITHUB_WEBHOOK_SECRET.get_secret_value():
                problems.append("GITHUB_WEBHOOK_SECRET is required")
            if len(self.SESSION_SECRET.get_secret_value()) < MIN_SESSION_SECRET_LENGTH:
                problems.append(
                    f"SESSION_SECRET must be at least {MIN_SESSION_SECRET_LENGTH} characters"
                )
            if (
                not self.GITHUB_OAUTH_CLIENT_ID
                or not self.GITHUB_OAUTH_CLIENT_SECRET.get_secret_value()
            ):
                problems.append(
                    "GITHUB_OAUTH_CLIENT_ID and GITHUB_OAUTH_CLIENT_SECRET are required"
                )
            if not self.allowed_users and not self.allowed_orgs:
                problems.append("AUTH_ALLOWED_USERS or AUTH_ALLOWED_ORGS must be set")
            if problems:
                raise ValueError("Insecure production configuration: " + "; ".join(problems))
        elif not self.SESSION_SECRET.get_secret_value():
            # Development convenience: sessions are invalidated on every restart
            self.SESSION_SECRET = SecretStr(secrets.token_urlsafe(48))
        return self


settings = Settings()
