"""LLM provider selection from the dashboard."""

from typing import Any

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.core.security import Principal, require_admin, require_read
from app.llm import factory

router = APIRouter(prefix="/api/llm", tags=["llm"])
log = structlog.get_logger()


class ProviderUpdate(BaseModel):
    provider: factory.Provider


async def _ollama_availability() -> tuple[bool, str | None]:
    """Whether the Ollama server is reachable and has the configured model."""
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/tags")
            response.raise_for_status()
    except httpx.HTTPError:
        return False, f"Ollama is not running at {settings.OLLAMA_BASE_URL}"
    names = {m.get("name", "") for m in response.json().get("models", [])}
    wanted = settings.OLLAMA_MODEL
    if wanted not in names and f"{wanted}:latest" not in names:
        return False, f"Model {wanted} is not downloaded (run: ollama pull {wanted})"
    return True, None


def _gemini_availability() -> tuple[bool, str | None]:
    if settings.GEMINI_API_KEY.get_secret_value():
        return True, None
    return False, "GEMINI_API_KEY is not set"


async def _describe() -> dict[str, Any]:
    gemini_ok, gemini_reason = _gemini_availability()
    ollama_ok, ollama_reason = await _ollama_availability()
    active = factory.provider_name()
    return {
        "provider": active,
        "model": factory.model_name(active),
        "rate_limited": factory.uses_rate_limiter(),
        "providers": [
            {
                "id": "gemini",
                "label": "Gemini (Google API)",
                "model": factory.model_name("gemini"),
                "available": gemini_ok,
                "reason": gemini_reason,
            },
            {
                "id": "ollama",
                "label": "Ollama (local)",
                "model": factory.model_name("ollama"),
                "available": ollama_ok,
                "reason": ollama_reason,
            },
        ],
    }


@router.get("")
async def get_llm_settings(_: Principal = Depends(require_read)) -> dict[str, Any]:
    """Active provider and availability of each option."""
    return await _describe()


@router.put("")
async def set_llm_provider(
    body: ProviderUpdate, principal: Principal = Depends(require_admin)
) -> dict[str, Any]:
    """Switch the provider used by reviews started from now on (administrators only)."""
    if body.provider == "gemini":
        available, reason = _gemini_availability()
    else:
        available, reason = await _ollama_availability()
    if not available:
        raise HTTPException(status_code=409, detail=reason)

    await factory.set_runtime_provider(body.provider)
    log.info("llm_provider_changed", provider=body.provider, by=principal.login)
    return await _describe()
