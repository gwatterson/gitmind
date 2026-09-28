"""A small, explicit taxonomy of common review problems.

Agents name the same problem differently (sql-injection, s89, SQLInjection) and
small models sometimes report problems outside their specialty (the performance
agent flagging an XSS). Mapping findings to a known concept lets the synthesis
merge duplicates across agents and file each problem under the right category.
Unknown problems are left untouched.
"""

import re
from dataclasses import dataclass

from app.graph.state import Finding


@dataclass(frozen=True)
class Concept:
    name: str
    category: str  # the specialist that owns the problem
    markers: tuple[str, ...]  # lowercase substrings of rule id, message or CWE


CONCEPTS = (
    Concept("sql-injection", "security", ("sql injection", "sql-injection", "sqli", "cwe-89")),
    Concept("xss", "security", ("xss", "cross-site scripting", "cross site scripting", "cwe-79")),
    Concept(
        "hardcoded-secret",
        "security",
        (
            "hardcoded secret",
            "hardcoded-secret",
            "hard-coded",
            "hardcoded api",
            "hardcoded password",
            "hardcoded credential",
            "hardcoded key",
            "hardcoded token",
            "cwe-798",
        ),
    ),
    Concept("command-injection", "security", ("command injection", "command-injection", "cwe-78")),
    Concept(
        "path-traversal",
        "security",
        ("path traversal", "path-traversal", "directory traversal", "cwe-22"),
    ),
    Concept(
        "insecure-deserialization",
        "security",
        ("deserialization", "pickle.load", "yaml.load", "cwe-502"),
    ),
    Concept("ssrf", "security", ("ssrf", "server-side request forgery", "cwe-918")),
    Concept(
        "n-plus-one",
        "performance",
        (
            "n+1",
            "n-plus-one",
            "n plus one",
            "query inside a loop",
            "queries inside a loop",
            "query in a loop",
            "queries in a loop",
        ),
    ),
    Concept("string-concat-loop", "performance", ("string concatenation", "string-concatenation")),
    Concept(
        "complexity",
        "quality",
        (
            "cyclomatic",
            "cognitive complexity",
            "function-complexity",
            "too many parameters",
            "too-many-parameters",
            "deeply nested",
            "deep nesting",
        ),
    ),
)


_SEPARATORS = re.compile(r"[\s_\-/:,()]+")


def _words(text: str) -> set[str]:
    words = (w.strip(".;!?'\"`") for w in _SEPARATORS.split(text.lower()))
    return {w for w in words if w}


def concept_of(finding: Finding) -> Concept | None:
    """The known concept a finding describes, if any (first match wins).

    A marker matches when all its words appear in the rule id, message or CWE,
    in any order: "hardcoded secret" matches "hardcoded-api-secret".
    """
    words = _words(
        " ".join(
            str(part)
            for part in (finding.get("rule_id"), finding.get("message"), finding.get("cwe"))
            if part
        )
    )
    for concept in CONCEPTS:
        if any(_words(marker) <= words for marker in concept.markers):
            return concept
    return None


def _is_opaque_rule(rule_id: str) -> bool:
    """Codes such as s89 or 752 (models imitate static analyzers) say nothing to a reader."""
    return bool(re.fullmatch(r"[a-z]{0,3}-?\d+", rule_id.lower()))


def assign_owner_category(finding: Finding) -> Finding:
    """File a finding under the category that owns its concept (the agent is kept).

    Opaque rule codes are replaced by the concept name when the concept is known.
    """
    concept = concept_of(finding)
    if concept is None:
        return finding
    updates: dict[str, str] = {}
    if concept.category != finding.get("category"):
        updates["category"] = concept.category
    if _is_opaque_rule(finding.get("rule_id", "")):
        updates["rule_id"] = concept.name
    if not updates:
        return finding
    return Finding(**{**finding, **updates})  # type: ignore[typeddict-item]
