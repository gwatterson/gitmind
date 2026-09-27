"""Structured logging setup with secret masking."""

import logging
import re
from collections.abc import MutableMapping
from typing import Any

import structlog

REDACTED = "[REDACTED]"

# Keys whose values are never written to the logs
_SENSITIVE_KEY = re.compile(
    r"(token|secret|password|api_key|apikey|authorization|private_key|cookie|session)",
    re.IGNORECASE,
)

# Credential formats that must be masked even inside free-text values
_SENSITIVE_VALUE = re.compile(
    r"(gh[pousr]_[A-Za-z0-9]{20,}"  # GitHub tokens
    r"|github_pat_[A-Za-z0-9_]{20,}"  # GitHub fine-grained tokens
    r"|AIza[0-9A-Za-z_\-]{30,}"  # Google API keys
    r"|gm_[A-Za-z0-9_\-]{20,}"  # GitMind API keys
    r"|sk-[A-Za-z0-9_\-]{20,})"  # OpenAI/Anthropic style keys
)


def _mask(value: Any) -> Any:
    if isinstance(value, str):
        return _SENSITIVE_VALUE.sub(REDACTED, value)
    if isinstance(value, dict):
        return {
            k: REDACTED if _SENSITIVE_KEY.search(str(k)) else _mask(v) for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return type(value)(_mask(v) for v in value)
    return value


def mask_secrets(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """structlog processor: redact sensitive keys and credential-looking strings."""
    for key, value in list(event_dict.items()):
        if _SENSITIVE_KEY.search(key):
            event_dict[key] = REDACTED
        else:
            event_dict[key] = _mask(value)
    return event_dict


def configure_logging(level: str = "INFO", json_logs: bool = False) -> None:
    """Configure stdlib logging and structlog. JSON output is meant for production."""
    logging.basicConfig(format="%(message)s", level=level.upper(), force=True)

    renderer: Any = (
        structlog.processors.JSONRenderer() if json_logs else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            mask_secrets,
            renderer,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
