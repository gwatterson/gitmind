"""Synthesis: deduplication, ordering, verdict and scope notes."""

from app.graph.state import Finding
from app.graph.synthesis import (
    deduplicate_findings,
    determine_verdict,
    fallback_summary,
    scope_notes,
    sort_findings,
)


def _finding(**overrides) -> Finding:
    base = {
        "file": "app.py",
        "line": 10,
        "severity": "medium",
        "category": "quality",
        "rule_id": "rule",
        "message": "Something is wrong",
        "suggestion": "",
        "agent": "quality",
    }
    base.update(overrides)
    return Finding(**base)  # type: ignore[typeddict-item]


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


def test_findings_on_nearby_lines_with_similar_messages_are_merged():
    findings = [
        _finding(
            line=10,
            severity="medium",
            rule_id="sql-string",
            category="security",
            message="User input is concatenated into the SQL query",
        ),
        _finding(
            line=11,
            severity="high",
            rule_id="sql-injection",
            category="security",
            message="User input concatenated into SQL query allows injection",
        ),
    ]
    deduped = deduplicate_findings(findings)
    assert len(deduped) == 1
    assert deduped[0]["severity"] == "high"  # the most severe one is kept


def test_different_problems_close_together_are_kept():
    findings = [
        _finding(line=10, rule_id="n-plus-1", message="Query inside a loop"),
        _finding(line=11, rule_id="bare-except", message="Exception swallowed silently"),
    ]
    assert len(deduplicate_findings(findings)) == 2


def test_same_rule_far_apart_is_kept():
    findings = [_finding(line=10), _finding(line=40)]
    assert len(deduplicate_findings(findings)) == 2


def test_unsure_high_finding_does_not_block_the_pr():
    unsure = [_finding(severity="high", confidence=0.3)]
    sure = [_finding(severity="high", confidence=0.9)]
    assert determine_verdict(unsure, min_confidence=0.6) == "comment"
    assert determine_verdict(sure, min_confidence=0.6) == "request_changes"


def test_findings_without_confidence_are_treated_as_certain():
    assert (
        determine_verdict([_finding(severity="critical")], min_confidence=0.6) == "request_changes"
    )


def test_scope_notes_list_skipped_files_and_failed_agents():
    state = {"skipped_files": [{"filename": "package-lock.json", "reason": "excluded"}]}
    notes = scope_notes(state, ["performance"])  # type: ignore[arg-type]
    assert "Incomplete review" in notes and "performance" in notes
    assert "`package-lock.json`: excluded" in notes


def test_scope_notes_empty_when_everything_was_reviewed():
    assert scope_notes({}, []) == ""  # type: ignore[arg-type]


def test_fallback_summary_is_markdown_without_the_llm():
    summary = fallback_summary(
        [_finding(severity="high", line=3, message="Bad thing"), _finding(severity="low")],
        "request_changes",
    )
    assert summary.startswith("### Overall assessment")
    assert "`app.py:3` Bad thing" in summary
    assert "- High: 1" in summary and "- Low: 1" in summary
