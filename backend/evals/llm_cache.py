"""Disk cache of LLM responses, installed as the LangChain global cache.

Every model call of the pipeline goes through LangChain, so the cache sees each
call without any change to the agents. Entries are keyed by provider, model,
the serialized prompt and the call parameters LangChain exposes (e.g. the
structured output schema): changing a prompt, the model or a schema misses the
cache, rerunning the same configuration replays the recorded answers for free.

The cache also measures every call of the case being evaluated (see CallStats):
duration, tokens and whether the answer was live or replayed. Replayed calls
report the duration recorded when the answer was generated.
"""

import hashlib
import json
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from langchain_core.caches import RETURN_VAL_TYPE, BaseCache
from langchain_core.messages import messages_from_dict, messages_to_dict
from langchain_core.outputs import ChatGeneration, Generation

from app.llm import factory

CacheMode = Literal["use", "replay", "refresh", "off"]


class CacheMissError(RuntimeError):
    """Replay mode found no recorded answer for a call."""


@dataclass
class CallStats:
    """LLM usage of one evaluated case."""

    live_calls: int = 0
    cached_calls: int = 0
    missing_calls: int = 0  # replay mode only
    llm_seconds: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    purposes: list[str] = field(default_factory=list)

    @property
    def calls(self) -> int:
        return self.live_calls + self.cached_calls

    def add(self, elapsed: float, usage: dict[str, Any], *, cached: bool) -> None:
        if cached:
            self.cached_calls += 1
        else:
            self.live_calls += 1
        self.llm_seconds += elapsed
        self.input_tokens += int(usage.get("input_tokens") or 0)
        self.output_tokens += int(usage.get("output_tokens") or 0)


_current: ContextVar[CallStats | None] = ContextVar("eval_call_stats", default=None)


@contextmanager
def track_calls(stats: CallStats) -> Iterator[CallStats]:
    """Attribute the LLM calls made inside this block (and its tasks) to `stats`."""
    token = _current.set(stats)
    try:
        yield stats
    finally:
        _current.reset(token)


def _usage(generations: Sequence[Generation]) -> dict[str, Any]:
    for generation in generations:
        if isinstance(generation, ChatGeneration):
            usage = getattr(generation.message, "usage_metadata", None)
            if usage:
                return dict(usage)
    return {}


class DiskCache(BaseCache):
    """One JSON file per answer, grouped by model: easy to inspect, diff and commit."""

    def __init__(self, directory: Path, mode: CacheMode = "use") -> None:
        self.directory = directory
        self.mode = mode
        self._started: dict[str, float] = {}
        self.used_keys: set[str] = set()

    # LangChain calls the async methods from async code; the sync ones are not used
    def lookup(self, prompt: str, llm_string: str) -> RETURN_VAL_TYPE | None:
        raise NotImplementedError("the evaluation runs the pipeline asynchronously")

    def update(self, prompt: str, llm_string: str, return_val: RETURN_VAL_TYPE) -> None:
        raise NotImplementedError("the evaluation runs the pipeline asynchronously")

    def clear(self, **kwargs: Any) -> None:
        for path in self.directory.rglob("*.json"):
            path.unlink()

    @staticmethod
    def model_dir_name() -> str:
        raw = f"{factory.provider_name()}-{factory.model_name()}"
        return "".join(c if c.isalnum() or c in ".-" else "-" for c in raw)

    @staticmethod
    def key(prompt: str, llm_string: str) -> str:
        material = json.dumps([factory.provider_name(), factory.model_name(), llm_string, prompt])
        return hashlib.sha256(material.encode()).hexdigest()

    def _path(self, key: str) -> Path:
        return self.directory / self.model_dir_name() / f"{key}.json"

    async def alookup(self, prompt: str, llm_string: str) -> RETURN_VAL_TYPE | None:
        key = self.key(prompt, llm_string)
        stats = _current.get()
        path = self._path(key)
        if self.mode in ("use", "replay") and path.is_file():
            entry = json.loads(path.read_text(encoding="utf-8"))
            generations: list[Generation] = [
                ChatGeneration(message=message) for message in messages_from_dict(entry["messages"])
            ]
            self.used_keys.add(key)
            if stats is not None:
                stats.add(entry.get("elapsed_seconds", 0.0), _usage(generations), cached=True)
            return generations
        if self.mode == "replay":
            if stats is not None:
                stats.missing_calls += 1
            raise CacheMissError(
                "No recorded answer for this call: run the evaluation with the model "
                "(cache mode 'use') to record it."
            )
        self._started[key] = time.monotonic()
        return None

    async def aupdate(self, prompt: str, llm_string: str, return_val: RETURN_VAL_TYPE) -> None:
        key = self.key(prompt, llm_string)
        elapsed = time.monotonic() - self._started.pop(key, time.monotonic())
        stats = _current.get()
        if stats is not None:
            stats.add(elapsed, _usage(return_val), cached=False)
        if self.mode == "off":
            return
        messages = [g.message for g in return_val if isinstance(g, ChatGeneration)]
        if len(messages) != len(return_val):
            return  # not a chat answer: nothing this pipeline produces
        entry = {
            "provider": factory.provider_name(),
            "model": factory.model_name(),
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "elapsed_seconds": round(elapsed, 3),
            "messages": messages_to_dict(messages),
        }
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(entry, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
        )
        self.used_keys.add(key)

    def prune(self) -> int:
        """Delete the answers of the current model not used by this run."""
        removed = 0
        for path in (self.directory / self.model_dir_name()).glob("*.json"):
            if path.stem not in self.used_keys:
                path.unlink()
                removed += 1
        return removed
