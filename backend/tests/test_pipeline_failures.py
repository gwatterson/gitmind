"""End-to-end graph runs with fake LLM calls: findings, partial failures, quota, publishing."""

from unittest.mock import AsyncMock

import pytest

import app.graph.graph as graph_module
from app.config import settings
from app.db import crud
from app.graph import synthesis
from app.graph.agents import base
from app.graph.prompts import prompt_versions
from app.graph.schemas import AgentReview, ReviewFinding
from app.rate_limiter import DailyQuotaExhaustedError
from app.services import publisher
from app.services.publisher import PublishResult

PATCH = "@@ -1,3 +1,4 @@\n import os\n+query = 'SELECT * FROM t WHERE id=' + uid\n cursor.execute(query)\n x = 1"
FILES = [
    {"filename": "app.py", "language": "python", "patch": PATCH, "additions": 1, "deletions": 0}
]


def _finding(agent: str, **overrides) -> ReviewFinding:
    data = {
        "file": "app.py",
        "line": 2,
        "severity": "low",
        "rule_id": f"{agent}-rule",
        "message": f"{agent} issue",
        "confidence": 0.9,
    }
    data.update(overrides)
    return ReviewFinding(**data)


@pytest.fixture
def pipeline(monkeypatch):
    """Route LLM calls by purpose; each test decides how every agent behaves."""
    behaviors: dict[str, object] = {}

    async def fake_structured(messages, schema, **kwargs):
        agent = kwargs["purpose"].removesuffix("_agent")
        behavior = behaviors.get(agent, [])
        if isinstance(behavior, BaseException):
            raise behavior
        return AgentReview(findings=behavior)

    monkeypatch.setattr(base, "invoke_structured", fake_structured)
    monkeypatch.setattr(
        synthesis, "invoke_text", AsyncMock(return_value="### Overall assessment\nOK")
    )
    publish = AsyncMock(return_value=PublishResult(posted=True, comments_posted=1))
    monkeypatch.setattr(publisher, "publish_review", publish)

    def configure(**agents):
        behaviors.update(agents)
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
    assert stored["llm_provider"] == "gemini"
    assert stored["llm_model"] == settings.GEMINI_MODEL
    assert stored["prompt_versions"] == prompt_versions()
    publish.assert_awaited_once_with(stored["id"], human_approved=False)


async def test_findings_are_validated_and_stored_with_their_metadata(pipeline):
    pipeline(
        security=[
            _finding("security", severity="high", cwe="89", line=2, evidence="query = ..."),
            _finding("security", file="ghost.py"),  # file not in the PR: dropped
            _finding("security", line=5, rule_id="near", message="close to the diff"),
        ]
    )
    _, stored = await _run()

    findings = {f["rule_id"]: f for f in await crud.get_findings(stored["id"])}
    assert set(findings) == {"security-rule", "near"}
    assert findings["security-rule"]["cwe"] == "CWE-89"
    assert findings["security-rule"]["confidence"] == 0.9
    assert findings["security-rule"]["line"] == 2
    assert findings["near"]["line"] == 4  # moved to the nearest line of the diff
    assert stored["verdict"] == "request_changes"


async def test_two_agents_failing_in_parallel_do_not_crash_the_graph(pipeline):
    # Regression: concurrent writes to the same state key raised InvalidUpdateError
    pipeline(
        security=RuntimeError("boom"),
        quality=RuntimeError("boom"),
        performance=[_finding("performance")],
    )
    result, stored = await _run()

    assert stored["status"] == "completed"
    assert {e["agent"] for e in result["errors"]} == {"security", "quality"}
    assert "Incomplete review" in stored["summary"]


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
    publish = pipeline(performance=[_finding("performance")])
    _, stored = await _run()

    assert stored["status"] == "hitl_pending"
    publish.assert_not_awaited()


async def test_summary_falls_back_when_the_summary_call_fails(pipeline, monkeypatch):
    pipeline(quality=[_finding("quality", severity="medium")])
    monkeypatch.setattr(synthesis, "invoke_text", AsyncMock(side_effect=RuntimeError("down")))
    _, stored = await _run()

    assert stored["status"] == "completed"
    assert stored["summary"].startswith("### Overall assessment")
