"""Verifier node: confirmed findings are kept, rejected ones are stored as suppressed."""

from unittest.mock import AsyncMock

import pytest

import app.graph.graph as graph_module
from app.config import settings
from app.db import crud
from app.graph import synthesis, verifier
from app.graph.agents import base
from app.graph.schemas import AgentReview, ReviewFinding, VerifierReview, VerifierVerdict
from app.services import publisher
from app.services.publisher import PublishResult
from tests.test_pipeline_failures import FILES


def _finding(line: int, rule: str) -> ReviewFinding:
    return ReviewFinding(
        file="app.py",
        line=line,
        severity="high",
        rule_id=rule,
        message=f"{rule} problem",
        confidence=0.9,
    )


@pytest.fixture
def reviewed(monkeypatch):
    """Security agent reports two findings; the test decides what the verifier answers."""
    monkeypatch.setattr(settings, "VERIFIER_ENABLED", True)
    monkeypatch.setattr(settings, "VERIFIER_MIN_CONFIDENCE", 0.5)

    async def agents(messages, schema, **kwargs):
        if kwargs["purpose"] == "security_agent":
            return AgentReview(findings=[_finding(2, "sql-injection"), _finding(3, "weak-hash")])
        return AgentReview(findings=[])

    monkeypatch.setattr(base, "invoke_structured", agents)
    monkeypatch.setattr(synthesis, "invoke_text", AsyncMock(return_value="Summary"))
    monkeypatch.setattr(
        publisher, "publish_review", AsyncMock(return_value=PublishResult(posted=True))
    )

    def answer(outcome: object) -> AsyncMock:
        check = AsyncMock(side_effect=outcome if isinstance(outcome, Exception) else None)
        if not isinstance(outcome, Exception):
            check.return_value = outcome
        monkeypatch.setattr(verifier, "invoke_structured", check)
        return check

    return answer


async def _run() -> str:
    review = await crud.create_review(repo="octo/demo", pr_number=1, commit_id="sha")
    await graph_module.run_review(review["id"], "octo/demo", 1, "sha", FILES)
    return review["id"]


async def test_rejected_and_unsure_findings_are_suppressed(reviewed):
    check = reviewed(
        VerifierReview(
            verdicts=[
                VerifierVerdict(id=0, real=True, confidence=0.95, reason="query built from input"),
                VerifierVerdict(id=1, real=True, confidence=0.3, reason="only a checksum"),
            ]
        )
    )
    review_id = await _run()

    check.assert_awaited_once()  # one call for the only file with findings
    published = await crud.get_findings(review_id)
    assert [(f["rule_id"], f["confidence"]) for f in published] == [("sql-injection", 0.95)]
    everything = await crud.get_findings(review_id, include_suppressed=True)
    suppressed = [f for f in everything if f["suppressed"]]
    assert [(f["rule_id"], f["verifier_note"]) for f in suppressed] == [
        ("weak-hash", "only a checksum")
    ]
    stats = await crud.get_review_stats()
    assert stats["total_findings"] == 1


async def test_verifier_failure_keeps_the_agent_findings(reviewed):
    reviewed(RuntimeError("verifier down"))
    review_id = await _run()
    review = await crud.get_review(review_id)
    assert review is not None and review["status"] == "completed"
    assert len(await crud.get_findings(review_id)) == 2


async def test_findings_without_an_answer_are_kept(reviewed):
    reviewed(VerifierReview(verdicts=[VerifierVerdict(id=1, real=False, confidence=0.1)]))
    review_id = await _run()
    assert [f["rule_id"] for f in await crud.get_findings(review_id)] == ["sql-injection"]


async def test_disabled_verifier_is_not_called(reviewed, monkeypatch):
    check = reviewed(VerifierReview())
    monkeypatch.setattr(settings, "VERIFIER_ENABLED", False)
    review_id = await _run()
    check.assert_not_awaited()
    assert len(await crud.get_findings(review_id)) == 2
