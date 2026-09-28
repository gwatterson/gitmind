"""Concept taxonomy: cross-agent duplicates and owner categories."""

import pytest

from app.graph.state import Finding
from app.graph.synthesis import deduplicate_findings
from app.graph.taxonomy import assign_owner_category, concept_of


def _finding(**overrides) -> Finding:
    base = {
        "file": "app.py",
        "line": 17,
        "severity": "high",
        "category": "security",
        "rule_id": "rule",
        "message": "Problem",
        "suggestion": "",
        "agent": "security",
    }
    base.update(overrides)
    return Finding(**base)  # type: ignore[typeddict-item]


@pytest.mark.parametrize(
    ("overrides", "concept"),
    [
        ({"rule_id": "sql-injection"}, "sql-injection"),
        ({"rule_id": "s89", "cwe": "CWE-89"}, "sql-injection"),
        ({"message": "Cross-site scripting through unescaped input"}, "xss"),
        ({"rule_id": "hardcoded-api-secret"}, "hardcoded-secret"),
        ({"rule_id": "n-plus-one-query"}, "n-plus-one"),
        ({"message": "Cyclomatic complexity of 16"}, "complexity"),
        ({"rule_id": "magic-number", "message": "Use a named constant"}, None),
    ],
)
def test_concept_of(overrides, concept):
    found = concept_of(_finding(**overrides))
    assert (found.name if found else None) == concept


def test_problem_reported_by_the_wrong_specialist_moves_to_the_owner_category():
    moved = assign_owner_category(
        _finding(category="performance", agent="performance", rule_id="xss-vulnerability")
    )
    assert moved["category"] == "security"
    assert moved["agent"] == "performance"  # who found it is kept


def test_opaque_rule_codes_are_replaced_by_the_concept_name():
    renamed = assign_owner_category(_finding(rule_id="s89", cwe="CWE-89"))
    assert renamed["rule_id"] == "sql-injection"
    kept = assign_owner_category(_finding(rule_id="unsafe-query", cwe="CWE-89"))
    assert kept["rule_id"] == "unsafe-query"


def test_same_problem_from_three_agents_becomes_one_finding():
    findings = [
        _finding(agent="security", severity="critical", rule_id="s89", cwe="CWE-89"),
        _finding(agent="performance", category="performance", rule_id="sql-injection"),
        _finding(
            agent="quality", category="quality", line=16, message="Vulnerable to SQL injection"
        ),
    ]
    merged = deduplicate_findings([assign_owner_category(f) for f in findings])
    assert len(merged) == 1
    assert merged[0]["severity"] == "critical"
    assert merged[0]["category"] == "security"


def test_different_concepts_on_the_same_line_are_kept():
    findings = [
        _finding(rule_id="sql-injection"),
        _finding(rule_id="n-plus-one-query", category="performance", agent="performance"),
    ]
    assert len(deduplicate_findings(findings)) == 2
