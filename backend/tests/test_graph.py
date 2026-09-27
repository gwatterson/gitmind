"""Tests for the LangGraph review pipeline."""

from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage

from app.graph import supervisor
from app.graph.state import Finding
from app.graph.synthesis import deduplicate_findings, determine_verdict, sort_findings

# ──────────────────────────────────────────────
# Synthesis / Verdict Tests
# ──────────────────────────────────────────────


class _FakeLLM:
    """Stands in for ChatGoogleGenerativeAI and returns a canned reply."""

    reply = ""

    def __init__(self, **kwargs):
        pass

    async def ainvoke(self, messages):
        return AIMessage(content=self.reply)


def _supervisor_state(filenames):
    files = [
        {"filename": name, "language": "python", "patch": "+x = 1", "additions": 1, "deletions": 0}
        for name in filenames
    ]
    return {"review_id": "r1", "repo": "o/r", "pr_number": 1, "files": files}


@pytest.fixture
def fake_supervisor_llm(monkeypatch):
    monkeypatch.setattr(supervisor, "ChatGoogleGenerativeAI", _FakeLLM)
    monkeypatch.setattr(supervisor.rate_limiter, "acquire", AsyncMock())
    monkeypatch.setattr(supervisor.crud, "create_event", AsyncMock())
    return _FakeLLM


async def test_supervisor_parses_json_code_block(fake_supervisor_llm):
    """The supervisor extracts assignments from a fenced JSON reply."""
    fake_supervisor_llm.reply = (
        "Here is the plan:\n```json\n"
        '{"security_files": ["a.py", "b.py"], "quality_files": ["a.py"], '
        '"performance_files": ["b.py"], "reasoning": "ok"}\n```'
    )

    result = await supervisor.supervisor_node(_supervisor_state(["a.py", "b.py"]))

    assert result["security_files"] == ["a.py", "b.py"]
    assert result["quality_files"] == ["a.py"]
    assert result["performance_files"] == ["b.py"]


async def test_supervisor_falls_back_to_all_agents_on_invalid_json(fake_supervisor_llm):
    """An unparsable reply sends every file to every agent."""
    fake_supervisor_llm.reply = "I cannot answer in JSON, sorry."

    result = await supervisor.supervisor_node(_supervisor_state(["a.py", "b.py"]))

    for key in ("security_files", "quality_files", "performance_files"):
        assert result[key] == ["a.py", "b.py"]


async def test_supervisor_with_no_files_skips_llm(fake_supervisor_llm):
    """A PR without files completes without calling the LLM."""
    result = await supervisor.supervisor_node(_supervisor_state([]))

    assert result["security_files"] == []
    supervisor.rate_limiter.acquire.assert_not_called()


def test_synthesis_deduplication():
    """Identical findings (same file + line + rule_id) should be merged."""
    findings = [
        Finding(
            file="app.py",
            line=10,
            severity="high",
            category="security",
            rule_id="sql-injection",
            message="SQL injection",
            suggestion="",
            agent="security",
        ),
        Finding(
            file="app.py",
            line=10,
            severity="high",
            category="security",
            rule_id="sql-injection",
            message="SQL injection duplicate",
            suggestion="",
            agent="quality",
        ),
        Finding(
            file="app.py",
            line=20,
            severity="medium",
            category="quality",
            rule_id="high-complexity",
            message="Complex function",
            suggestion="",
            agent="quality",
        ),
    ]

    deduped = deduplicate_findings(findings)
    assert len(deduped) == 2, f"Expected 2 unique findings, got {len(deduped)}"


def test_verdict_logic_critical():
    """Critical finding → request_changes."""
    findings = [
        Finding(
            file="app.py",
            line=10,
            severity="critical",
            category="security",
            rule_id="sql-injection",
            message="",
            suggestion="",
            agent="security",
        ),
    ]
    verdict = determine_verdict(findings)
    assert verdict == "request_changes"


def test_verdict_logic_approve():
    """Only low/info findings → approve."""
    findings = [
        Finding(
            file="app.py",
            line=10,
            severity="low",
            category="quality",
            rule_id="naming",
            message="",
            suggestion="",
            agent="quality",
        ),
        Finding(
            file="app.py",
            line=20,
            severity="info",
            category="quality",
            rule_id="docs",
            message="",
            suggestion="",
            agent="quality",
        ),
    ]
    verdict = determine_verdict(findings)
    assert verdict == "approve"


def test_verdict_logic_comment():
    """Medium severity → comment."""
    findings = [
        Finding(
            file="app.py",
            line=10,
            severity="medium",
            category="quality",
            rule_id="complexity",
            message="",
            suggestion="",
            agent="quality",
        ),
    ]
    verdict = determine_verdict(findings)
    assert verdict == "comment"


def test_verdict_empty():
    """No findings → approve."""
    verdict = determine_verdict([])
    assert verdict == "approve"


def test_sort_findings():
    """Findings should be sorted by severity (critical first)."""
    findings = [
        Finding(
            file="a.py",
            line=1,
            severity="low",
            category="q",
            rule_id="",
            message="",
            suggestion="",
            agent="q",
        ),
        Finding(
            file="b.py",
            line=2,
            severity="critical",
            category="s",
            rule_id="",
            message="",
            suggestion="",
            agent="s",
        ),
        Finding(
            file="c.py",
            line=3,
            severity="medium",
            category="p",
            rule_id="",
            message="",
            suggestion="",
            agent="p",
        ),
        Finding(
            file="d.py",
            line=4,
            severity="high",
            category="s",
            rule_id="",
            message="",
            suggestion="",
            agent="s",
        ),
    ]

    sorted_f = sort_findings(findings)
    severities = [f["severity"] for f in sorted_f]
    assert severities == ["critical", "high", "medium", "low"]


async def test_supervisor_always_sends_every_file_to_security(fake_supervisor_llm):
    """Security coverage does not depend on the model, and invented paths are dropped."""
    fake_supervisor_llm.reply = (
        '{"security_files": ["a.py"], "quality_files": ["b.py", "ghost.py"], '
        '"performance_files": []}'
    )

    result = await supervisor.supervisor_node(_supervisor_state(["a.py", "b.py"]))

    assert result["security_files"] == ["a.py", "b.py"]
    assert result["quality_files"] == ["b.py"]
    assert result["performance_files"] == []
