"""One way to call the LLM: quota, timeout, retries and real token accounting."""

import asyncio
from collections.abc import Sequence
from typing import Any, TypeVar

import httpx
import structlog
from langchain_core.messages import BaseMessage
from pydantic import BaseModel
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.config import settings
from app.llm import factory
from app.rate_limiter import DailyQuotaExhaustedError, rate_limiter

log = structlog.get_logger()

SchemaT = TypeVar("SchemaT", bound=BaseModel)

_TRANSIENT_STATUS = {408, 429, 500, 502, 503, 504}
_TRANSIENT_MARKERS = (
    "429",
    "500",
    "502",
    "503",
    "504",
    "RESOURCE_EXHAUSTED",
    "UNAVAILABLE",
    "DEADLINE_EXCEEDED",
    "timed out",
    "overloaded",
)


class StructuredOutputError(Exception):
    """The model answered, but not with valid JSON for the requested schema."""


def estimate_tokens(text: str) -> int:
    """Conservative token estimate (about 3 characters per token for code).

    Used to plan batches and reserve quota; the real usage reported by the
    provider replaces the estimate after each call.
    """
    return len(text) // 3 + 1


def is_transient(error: BaseException) -> bool:
    """Errors worth retrying: timeouts, rate limits, overloaded or unreachable servers."""
    if isinstance(error, DailyQuotaExhaustedError):
        return False
    if isinstance(
        error, StructuredOutputError | TimeoutError | httpx.TransportError | ConnectionError
    ):
        return True
    status = getattr(error, "status_code", None) or getattr(error, "code", None)
    if isinstance(status, int) and status in _TRANSIENT_STATUS:
        return True
    text = str(error)
    return any(marker in text for marker in _TRANSIENT_MARKERS)


def _total_tokens(raw: Any, fallback: int) -> int:
    usage = getattr(raw, "usage_metadata", None) or {}
    total = usage.get("total_tokens") if isinstance(usage, dict) else None
    return int(total) if total else fallback


async def _call(runnable: Any, messages: Sequence[BaseMessage], estimated_tokens: int) -> Any:
    reservation = None
    if factory.uses_rate_limiter():
        reservation = await rate_limiter.acquire(estimated_tokens=estimated_tokens)
    result = await asyncio.wait_for(runnable.ainvoke(list(messages)), settings.LLM_TIMEOUT_SECONDS)
    if reservation is not None:
        raw = result.get("raw") if isinstance(result, dict) else result
        await rate_limiter.record_actual_tokens(reservation, _total_tokens(raw, estimated_tokens))
    return result


def _retrying() -> AsyncRetrying:
    return AsyncRetrying(
        stop=stop_after_attempt(settings.LLM_MAX_ATTEMPTS),
        wait=wait_exponential_jitter(initial=settings.LLM_RETRY_WAIT_SECONDS, max=30),
        retry=retry_if_exception(is_transient),
        reraise=True,
    )


async def invoke_structured(
    messages: Sequence[BaseMessage],
    schema: type[SchemaT],
    *,
    temperature: float = 0.1,
    max_output_tokens: int = 4096,
    purpose: str = "llm_call",
) -> SchemaT:
    """Call the model and return a validated `schema` instance."""
    model = factory.get_chat_model(temperature, max_output_tokens)
    runnable = model.with_structured_output(schema, include_raw=True)
    estimated = sum(estimate_tokens(str(m.content)) for m in messages) + max_output_tokens

    async for attempt in _retrying():
        with attempt:
            result = await _call(runnable, messages, estimated)
            parsed = result.get("parsed") if isinstance(result, dict) else result
            if not isinstance(parsed, schema):
                error = result.get("parsing_error") if isinstance(result, dict) else None
                log.warning(
                    "llm_invalid_structured_output",
                    purpose=purpose,
                    attempt=attempt.retry_state.attempt_number,
                    error=str(error)[:300] if error else None,
                )
                raise StructuredOutputError(f"{purpose}: model output did not match the schema")
            return parsed
    raise AssertionError("unreachable")  # pragma: no cover


async def invoke_text(
    messages: Sequence[BaseMessage],
    *,
    temperature: float = 0.2,
    max_output_tokens: int = 2048,
    purpose: str = "llm_call",
) -> str:
    """Call the model and return its text answer."""
    model = factory.get_chat_model(temperature, max_output_tokens)
    estimated = sum(estimate_tokens(str(m.content)) for m in messages) + max_output_tokens

    async for attempt in _retrying():
        with attempt:
            message = await _call(model, messages, estimated)
            return str(message.text).strip()
    raise AssertionError("unreachable")  # pragma: no cover
