"""LLM invocation (retries, validation, quota, token accounting), chunking and provider API."""

from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
import respx
from langchain_core.messages import AIMessage, HumanMessage

from app.config import settings
from app.graph.agents.base import build_batches, build_chunks, normalize_rule_id
from app.graph.schemas import AgentReview, ReviewFinding
from app.llm import factory, invoke
from app.llm.invoke import StructuredOutputError, invoke_structured, invoke_text, is_transient
from app.rate_limiter import DailyQuotaExhaustedError, Reservation


class FakeModel:
    """Chat model double: replays a list of outcomes (values or exceptions)."""

    def __init__(self, outcomes: list[Any]):
        self.outcomes = list(outcomes)
        self.calls = 0

    def with_structured_output(self, schema, include_raw=False):
        return self

    async def ainvoke(self, messages):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


@pytest.fixture
def model(monkeypatch):
    def install(outcomes: list[Any]) -> FakeModel:
        fake = FakeModel(outcomes)
        monkeypatch.setattr(factory, "get_chat_model", lambda *a, **k: fake)
        return fake

    return install


@pytest.fixture
def limiter(monkeypatch):
    reservation = Reservation(timestamp=0.0, tokens=0)
    acquire = AsyncMock(return_value=reservation)
    record = AsyncMock()
    monkeypatch.setattr(invoke.rate_limiter, "acquire", acquire)
    monkeypatch.setattr(invoke.rate_limiter, "record_actual_tokens", record)
    return acquire, record, reservation


def _parsed(review: AgentReview, total_tokens: int = 1234) -> dict:
    usage = {"input_tokens": 1000, "output_tokens": 234, "total_tokens": total_tokens}
    raw = AIMessage(content="", usage_metadata=usage)
    return {"raw": raw, "parsed": review, "parsing_error": None}


def _unparsed() -> dict:
    return {"raw": AIMessage(content="oops"), "parsed": None, "parsing_error": ValueError("bad")}


MESSAGES = [HumanMessage(content="review this")]


async def test_structured_call_records_real_token_usage(model, limiter):
    acquire, record, reservation = limiter
    model([_parsed(AgentReview(findings=[]), total_tokens=777)])

    result = await invoke_structured(MESSAGES, AgentReview)

    assert result == AgentReview(findings=[])
    acquire.assert_awaited_once()
    record.assert_awaited_once_with(reservation, 777)


async def test_invalid_structured_output_is_retried(model, limiter):
    good = AgentReview(findings=[])
    fake = model([_unparsed(), _parsed(good)])

    assert await invoke_structured(MESSAGES, AgentReview) == good
    assert fake.calls == 2


async def test_output_still_invalid_after_all_attempts_raises(model, limiter):
    fake = model([_unparsed() for _ in range(settings.LLM_MAX_ATTEMPTS)])

    with pytest.raises(StructuredOutputError):
        await invoke_structured(MESSAGES, AgentReview)
    assert fake.calls == settings.LLM_MAX_ATTEMPTS


async def test_transient_errors_are_retried_and_permanent_ones_are_not(model, limiter):
    fake = model([RuntimeError("503 UNAVAILABLE"), AIMessage(content="summary")])
    assert await invoke_text(MESSAGES) == "summary"
    assert fake.calls == 2

    fake = model([ValueError("invalid api key")])
    with pytest.raises(ValueError):
        await invoke_text(MESSAGES)
    assert fake.calls == 1


async def test_daily_quota_is_never_retried(model, limiter):
    acquire, _, _ = limiter
    acquire.side_effect = DailyQuotaExhaustedError("done for today")
    fake = model([AIMessage(content="never")])

    with pytest.raises(DailyQuotaExhaustedError):
        await invoke_text(MESSAGES)
    assert fake.calls == 0


async def test_local_models_skip_the_rate_limiter(model, limiter, monkeypatch):
    acquire, _, _ = limiter
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    model([AIMessage(content="hi")])

    assert await invoke_text(MESSAGES) == "hi"
    acquire.assert_not_awaited()


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (TimeoutError(), True),
        (httpx.ConnectError("refused"), True),
        (RuntimeError("429 RESOURCE_EXHAUSTED"), True),
        (StructuredOutputError("x"), True),
        (ValueError("bad request"), False),
        (DailyQuotaExhaustedError("x"), False),
    ],
)
def test_is_transient(error, expected):
    assert is_transient(error) is expected


def test_finding_schema_normalizes_model_quirks():
    finding = ReviewFinding(
        file="a.py",
        line=1,
        severity="Warning",
        rule_id="r",
        message="m",
        confidence=85,
        cwe="cwe 79",
    )
    assert finding.severity == "medium"
    assert finding.confidence == 0.85
    assert finding.cwe == "CWE-79"


# ──────────────────────────────────────────────
# Chunking
# ──────────────────────────────────────────────


def _big_file(hunks: int, lines_per_hunk: int, name: str = "big.py") -> dict:
    parts = []
    start = 1
    for _ in range(hunks):
        body = "\n".join(f"+line {i} " + "x" * 60 for i in range(lines_per_hunk))
        parts.append(f"@@ -{start},0 +{start},{lines_per_hunk} @@\n{body}")
        start += lines_per_hunk + 10
    return {"filename": name, "language": "python", "patch": "\n".join(parts)}


def test_small_file_is_one_chunk():
    chunks = build_chunks(_big_file(hunks=2, lines_per_hunk=3), budget_tokens=10_000)
    assert len(chunks) == 1
    assert chunks[0].parts == 1


def test_large_file_is_split_by_hunks_within_the_budget():
    chunks = build_chunks(_big_file(hunks=6, lines_per_hunk=40), budget_tokens=2_000)
    assert len(chunks) > 1
    assert all(c.tokens <= 2_000 for c in chunks)
    assert {c.parts for c in chunks} == {len(chunks)}


def test_huge_hunk_is_truncated_not_dropped():
    chunks = build_chunks(_big_file(hunks=1, lines_per_hunk=400), budget_tokens=1_000)
    assert len(chunks) == 1
    assert "hunk truncated" in chunks[0].text


def test_batches_respect_the_budget():
    chunks = [
        chunk for n in range(4) for chunk in build_chunks(_big_file(1, 30, name=f"f{n}.py"), 10_000)
    ]
    batches = build_batches(chunks, budget_tokens=chunks[0].tokens * 2)
    assert [len(b) for b in batches] == [2, 2]


def test_ollama_budget_fits_the_context_window(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(settings, "OLLAMA_NUM_CTX", 8192)
    assert factory.input_token_budget(max_output_tokens=2048) == 8192 - 2048 - 1500


# ──────────────────────────────────────────────
# Provider selection API
# ──────────────────────────────────────────────


def _mock_ollama(models: list[str]) -> None:
    respx.get("http://ollama.test:11434/api/tags").mock(
        return_value=httpx.Response(200, json={"models": [{"name": m} for m in models]})
    )


@respx.mock
async def test_llm_settings_report_availability(user_client):
    respx.route(host="test").pass_through()
    _mock_ollama(["qwen2.5-coder:7b"])

    body = (await user_client.get("/api/llm")).json()

    assert body["provider"] == "gemini"
    assert body["rate_limited"] is True
    providers = {p["id"]: p for p in body["providers"]}
    assert providers["gemini"]["available"] is True
    assert providers["ollama"] == {
        "id": "ollama",
        "label": "Ollama (local)",
        "model": "qwen2.5-coder:7b",
        "available": True,
        "reason": None,
    }


@respx.mock
async def test_admin_switches_provider_and_it_persists(admin_client):
    respx.route(host="test").pass_through()
    _mock_ollama(["qwen2.5-coder:7b"])

    response = await admin_client.put("/api/llm", json={"provider": "ollama"})

    assert response.status_code == 200
    assert response.json()["provider"] == "ollama"
    assert response.json()["rate_limited"] is False
    factory.reset_runtime_provider()
    await factory.load_runtime_provider()  # as after a restart
    assert factory.provider_name() == "ollama"


@respx.mock
async def test_unavailable_provider_is_refused(admin_client):
    respx.route(host="test").pass_through()
    _mock_ollama(["llama3.2:latest"])

    response = await admin_client.put("/api/llm", json={"provider": "ollama"})

    assert response.status_code == 409
    assert "ollama pull qwen2.5-coder:7b" in response.json()["detail"]


async def test_only_admins_can_switch_provider(user_client):
    response = await user_client.put("/api/llm", json={"provider": "ollama"})
    assert response.status_code == 403


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("SQL_INJECTION", "sql-injection"),
        ("SQLInjection", "sql-injection"),
        ("sql-injection", "sql-injection"),
        ("NPlusOneQuery", "n-plus-one-query"),
        ("N+1 query", "n+1-query"),
        (" hardcoded secret ", "hardcoded-secret"),
    ],
)
def test_rule_ids_are_normalized(raw, expected):
    assert normalize_rule_id(raw) == expected
