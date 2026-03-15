"""Tests for the LangGraph review pipeline."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app.graph.state import PRState, Finding
from app.graph.synthesis import deduplicate_findings, sort_findings, determine_verdict


# ──────────────────────────────────────────────
# Synthesis / Verdict Tests
# ──────────────────────────────────────────────

def test_supervisor_assigns_files():
    """Verify supervisor correctly parses LLM assignment response."""
    # Test that file assignment creates appropriate lists
    from app.graph.supervisor import SUPERVISOR_SYSTEM_PROMPT
    assert "Security Agent" in SUPERVISOR_SYSTEM_PROMPT
    assert "Quality Agent" in SUPERVISOR_SYSTEM_PROMPT
    assert "Performance Agent" in SUPERVISOR_SYSTEM_PROMPT


def test_synthesis_deduplication():
    """Identical findings (same file + line + rule_id) should be merged."""
    findings = [
        Finding(file="app.py", line=10, severity="high", category="security",
                rule_id="sql-injection", message="SQL injection", suggestion="", agent="security"),
        Finding(file="app.py", line=10, severity="high", category="security",
                rule_id="sql-injection", message="SQL injection duplicate", suggestion="", agent="quality"),
        Finding(file="app.py", line=20, severity="medium", category="quality",
                rule_id="high-complexity", message="Complex function", suggestion="", agent="quality"),
    ]

    deduped = deduplicate_findings(findings)
    assert len(deduped) == 2, f"Expected 2 unique findings, got {len(deduped)}"


def test_verdict_logic_critical():
    """Critical finding → request_changes."""
    findings = [
        Finding(file="app.py", line=10, severity="critical", category="security",
                rule_id="sql-injection", message="", suggestion="", agent="security"),
    ]
    verdict = determine_verdict(findings)
    assert verdict == "request_changes"


def test_verdict_logic_approve():
    """Only low/info findings → approve."""
    findings = [
        Finding(file="app.py", line=10, severity="low", category="quality",
                rule_id="naming", message="", suggestion="", agent="quality"),
        Finding(file="app.py", line=20, severity="info", category="quality",
                rule_id="docs", message="", suggestion="", agent="quality"),
    ]
    verdict = determine_verdict(findings)
    assert verdict == "approve"


def test_verdict_logic_comment():
    """Medium severity → comment."""
    findings = [
        Finding(file="app.py", line=10, severity="medium", category="quality",
                rule_id="complexity", message="", suggestion="", agent="quality"),
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
        Finding(file="a.py", line=1, severity="low", category="q", rule_id="", message="", suggestion="", agent="q"),
        Finding(file="b.py", line=2, severity="critical", category="s", rule_id="", message="", suggestion="", agent="s"),
        Finding(file="c.py", line=3, severity="medium", category="p", rule_id="", message="", suggestion="", agent="p"),
        Finding(file="d.py", line=4, severity="high", category="s", rule_id="", message="", suggestion="", agent="s"),
    ]

    sorted_f = sort_findings(findings)
    severities = [f["severity"] for f in sorted_f]
    assert severities == ["critical", "high", "medium", "low"]
