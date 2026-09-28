"""Chat model factory: the rest of the code never imports a provider directly.

The provider comes from LLM_PROVIDER in the environment, unless an administrator
chose another one from the dashboard: that choice is stored in the database and
applies to reviews started afterwards.
"""

from functools import lru_cache
from typing import Literal

from langchain_core.language_models import BaseChatModel

from app.config import settings
from app.db import crud

Provider = Literal["gemini", "ollama"]
PROVIDERS: tuple[Provider, ...] = ("gemini", "ollama")
PROVIDER_SETTING_KEY = "llm_provider"

_runtime_provider: Provider | None = None


def provider_name() -> Provider:
    return _runtime_provider or settings.LLM_PROVIDER


def model_name(provider: Provider | None = None) -> str:
    provider = provider or provider_name()
    return settings.OLLAMA_MODEL if provider == "ollama" else settings.GEMINI_MODEL


async def load_runtime_provider() -> None:
    """Restore the provider chosen from the dashboard (called at startup)."""
    global _runtime_provider
    stored = await crud.get_app_setting(PROVIDER_SETTING_KEY)
    _runtime_provider = stored if stored in PROVIDERS else None


async def set_runtime_provider(provider: Provider) -> None:
    global _runtime_provider
    await crud.set_app_setting(PROVIDER_SETTING_KEY, provider)
    _runtime_provider = provider


def reset_runtime_provider() -> None:
    """Forget the dashboard choice (used by tests)."""
    global _runtime_provider
    _runtime_provider = None


def uses_rate_limiter() -> bool:
    """Local models have no quota: the rate limiter only guards the Gemini API."""
    return provider_name() == "gemini"


def input_token_budget(max_output_tokens: int) -> int:
    """Max estimated diff tokens per call, leaving room for prompt and answer."""
    budget = settings.LLM_INPUT_TOKEN_BUDGET
    if provider_name() == "ollama":
        # Everything must fit in the context window requested from Ollama
        prompt_overhead = 1_500
        budget = min(budget, settings.OLLAMA_NUM_CTX - max_output_tokens - prompt_overhead)
    return max(budget, 1_000)


@lru_cache(maxsize=16)
def _cached_model(
    provider: str, model: str, temperature: float, max_output_tokens: int
) -> BaseChatModel:
    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=model,
            base_url=settings.OLLAMA_BASE_URL,
            temperature=temperature,
            num_predict=max_output_tokens,
            num_ctx=settings.OLLAMA_NUM_CTX,
        )

    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=model,
        google_api_key=settings.GEMINI_API_KEY,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )


def get_chat_model(temperature: float, max_output_tokens: int) -> BaseChatModel:
    """Return a shared chat model instance for the configured provider."""
    return _cached_model(provider_name(), model_name(), temperature, max_output_tokens)
