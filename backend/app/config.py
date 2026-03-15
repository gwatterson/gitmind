"""Application settings via pydantic-settings. All values from environment variables."""

from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # Gemini LLM
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # Rate limiter (Tier 1 with 20% safety margin)
    RATE_LIMIT_RPM_MAX: int = 120       # 80% of 150 RPM
    RATE_LIMIT_RPD_MAX: int = 1200      # 80% of 1500 RPD
    RATE_LIMIT_TPM_MAX: int = 800_000   # 80% of 1M TPM

    # GitHub App
    GITHUB_APP_ID: str = ""
    GITHUB_PRIVATE_KEY_PATH: str = ""
    GITHUB_WEBHOOK_SECRET: str = ""
    GITHUB_TOKEN: str = ""

    # LangSmith (optional)
    LANGSMITH_API_KEY: str = ""
    LANGSMITH_TRACING: bool = False
    LANGCHAIN_PROJECT: str = "code-review-agent"

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./reviews.db"
    DATABASE_PATH: str = "./reviews.db"

    # App
    HITL_ENABLED: bool = False
    CORS_ORIGINS: str = "http://localhost:3000,https://your-frontend.vercel.app"
    LOG_LEVEL: str = "INFO"

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    model_config = {
        "env_file": ".env", 
        "env_file_encoding": "utf-8",
        "extra": "ignore"
    }


settings = Settings()
