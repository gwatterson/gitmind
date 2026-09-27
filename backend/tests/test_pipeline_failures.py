"""End-to-end graph runs with fake LLMs: partial failures, quota exhaustion, publishing."""

import json
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage

import app.graph.graph as graph_module
from app.config import settings
from app.db import crud
from app.graph import supervisor, synthesis
from app.graph.agents import performance, quality, security
from app.rate_limiter import DailyQuotaExhaustedError, rate_limiter
from app.services import publisher
from app.services.publisher import PublishResult

FILES = [
    {"filename": "app.py", "language": "python", "patch": "+x = 1", "additions": 1, "deletions": 0}
]
AGENT_MODULES = {"security": security, "quality": quality, "performance": performance}


class _TextLLM:
    """Fake chat model returning a fixed text reply."""

    def __init__(self, reply: str):
        self.reply = reply

    async def ainvoke(self, messages):
        return AIMessage(content=self.reply)


class _StructuredLLM:
    """Fake chat model for agents: returns a parsed review or raises."""

    def __init__(self, result=None, error: Exception | None = None):
        self.result = result
        self.error = error

    def with_structured_output(self, schema):
        return self

    async def ainvoke(self, messages):
        if self.error:
            raise self.error
        return self.result


def _factory(instance):
    return lambda **kwargs: instance


@pytest.fixture
def pipeline(monkeypatch):
    """Wire fake LLMs into every node; tests choose how each agent behaves."""
    monkeypatch.setattr(rate_limiter, "acquire", AsyncMock())
    assignments = {f"{name}_files": ["app.py"] for name in AGENT_MODULES}
    monkeypatch.setattr(
        supervisor, "ChatGoogleGenerativeAI", _factory(_TextLLM(json.dumps(assignments)))
    )
    monkeypatch.setattr(synthesis, "ChatGoogleGenerativeAI", _factory(_TextLLM("Summary.")))
    publish = AsyncMock(return_value=PublishResult(posted=True, comments_posted=1))
    monkeypatch.setattr(publisher, "publish_review", publish)

    def configure(**agents):
        for name, module in AGENT_MODULES.items():
            behavior = agents.get(name, "empty")
            review_cls = {
                "security": security.SecurityReview,
                "quality": quality.QualityReview,
                "performance": performance.PerformanceReview,
            }[name]
            if isinstance(behavior, Exception):
                llm = _StructuredLLM(error=behavior)
            elif behavior == "finding":
                finding_cls = module.FindingModel
                llm = _StructuredLLM(
                    review_cls(
                        findings=[
                            finding_cls(
                                file="app.py",
                                line=1,
                                severity="low",
                                category=name,
                                rule_id=f"{name}-rule",
                                message="Minor issue",
                            )
                        ]
                    )
                )
            else:
                llm = _StructuredLLM(review_cls(findings=[]))
            monkeypatch.setattr(module, "ChatGoogleGenerativeAI", _factory(llm))
        return publish

    return configure


async def _run() -> tuple[dict, dict]:
    review = await crud.create_review(repo="octo/demo", pr_number=1, commit_id="sha")
    result = await graph_module.run_review(review["id"], "octo/demo", 1, "sha", FILES)
    stored = await crud.get_review(review["id"])
    assert stored is not None
    return result, stored


async def test_clean_review_is_published_as_a_comment(pipeline):
    publish = pipeline()
    _, stored = await _run()

    assert stored["status"] == "completed"
    assert stored["verdict"] == "approve"
    publish.assert_awaited_once_with(stored["id"], human_approved=False)


async def test_two_agents_failing_in_parallel_do_not_crash_the_graph(pipeline):
    # Regression: concurrent writes to the same state key raised InvalidUpdateError
    pipeline(security=RuntimeError("boom"), quality=RuntimeError("boom"), performance="finding")
    result, stored = await _run()

    assert stored["status"] == "completed"
    assert {e["agent"] for e in result["errors"]} == {"security", "quality"}
    assert "security" in stored["summary"] and "incomplete" in stored["summary"]


async def test_partial_review_never_approves(pipeline):
    pipeline(security=RuntimeError("boom"))
    _, stored = await _run()
    assert stored["verdict"] == "comment"


async def test_all_agents_failing_marks_the_review_failed_and_skips_publishing(pipeline):
    publish = pipeline(
        security=RuntimeError("a"), quality=RuntimeError("b"), performance=RuntimeError("c")
    )
    _, stored = await _run()

    assert stored["status"] == "failed"
    assert "All review agents failed" in stored["error"]
    publish.assert_not_awaited()
    events = [e["event_type"] for e in await crud.get_events(stored["id"])]
    assert "review_error" in events


async def test_quota_exhaustion_stops_the_review(pipeline):
    publish = pipeline(security=DailyQuotaExhaustedError("Resets in 3.0 hours."))
    result, stored = await _run()

    assert result["status"] == "quota_exhausted"
    assert stored["status"] == "quota_exhausted"
    assert stored["completed_at"]
    publish.assert_not_awaited()


async def test_hitl_waits_for_a_human_instead_of_publishing(pipeline, monkeypatch):
    monkeypatch.setattr(settings, "HITL_ENABLED", True)
    publish = pipeline(performance="finding")
    _, stored = await _run()

    assert stored["status"] == "hitl_pending"
    publish.assert_not_awaited()
