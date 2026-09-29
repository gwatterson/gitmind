"""Match the findings of a review against the expected findings of a case.

A finding matches an expected finding when it is on the same file, its line is at
most LINE_TOLERANCE lines outside the expected range, and (for the main metrics)
it has the same category. Matching is one to one: the closest pairs are assigned
first, and further findings on an already matched problem count as duplicates
(neither true nor false positives, reported separately).
"""

from dataclasses import asdict, dataclass, field
from typing import Any

from evals.dataset import SEVERITY_RANK, Case, ExpectedFinding

LINE_TOLERANCE = 3


@dataclass
class Match:
    expected: int  # index in case.expected_findings
    finding: int  # index in the findings list
    distance: int  # 0 when the line is inside the expected range
    cwe_ok: bool | None  # None when the expected finding has no CWE
    severity_ok: bool


@dataclass
class CaseMatch:
    matches: list[Match] = field(default_factory=list)
    duplicates: list[int] = field(default_factory=list)
    false_positives: list[int] = field(default_factory=list)
    unplaced: list[int] = field(default_factory=list)  # line 0: only in the summary
    must_not_flag_hits: list[int] = field(default_factory=list)
    missed: list[int] = field(default_factory=list)  # expected findings not found
    # Same problems ignoring the category (localization only)
    located: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _severity_ok(finding: dict[str, Any], expected: ExpectedFinding) -> bool:
    rank = SEVERITY_RANK.get(str(finding.get("severity")), 0)
    return rank >= SEVERITY_RANK[expected.severity_min]


def _cwe_ok(finding: dict[str, Any], expected: ExpectedFinding) -> bool | None:
    if not expected.cwe:
        return None
    return finding.get("cwe") in expected.cwe


def _distance(finding: dict[str, Any], expected: ExpectedFinding) -> int | None:
    """Distance from the closest location of the expected problem, None if too far."""
    line = int(finding.get("line") or 0)
    if line <= 0:
        return None
    distances = [
        location.distance(line)
        for location in expected.locations
        if location.file == finding.get("file")
    ]
    if not distances or min(distances) > LINE_TOLERANCE:
        return None
    return min(distances)


def match_case(case: Case, findings: list[dict[str, Any]]) -> CaseMatch:
    result = CaseMatch()
    candidates: list[tuple[int, int, int]] = []  # (distance, expected, finding)
    located_expected: set[int] = set()
    for e_index, expected in enumerate(case.expected_findings):
        for f_index, finding in enumerate(findings):
            distance = _distance(finding, expected)
            if distance is None:
                continue
            located_expected.add(e_index)
            if finding.get("category") == expected.category:
                candidates.append((distance, e_index, f_index))

    matched_expected: set[int] = set()
    matched_findings: set[int] = set()
    for distance, e_index, f_index in sorted(candidates):
        if e_index in matched_expected or f_index in matched_findings:
            continue
        expected = case.expected_findings[e_index]
        finding = findings[f_index]
        result.matches.append(
            Match(
                expected=e_index,
                finding=f_index,
                distance=distance,
                cwe_ok=_cwe_ok(finding, expected),
                severity_ok=_severity_ok(finding, expected),
            )
        )
        matched_expected.add(e_index)
        matched_findings.add(f_index)

    duplicate_findings = {f for _, _, f in candidates} - matched_findings
    for f_index, finding in enumerate(findings):
        if f_index in matched_findings:
            continue
        if f_index in duplicate_findings:
            result.duplicates.append(f_index)
            continue
        result.false_positives.append(f_index)
        if not int(finding.get("line") or 0):
            result.unplaced.append(f_index)
        line = int(finding.get("line") or 0)
        if any(
            safe.file == finding.get("file") and safe.distance(line) == 0
            for safe in case.must_not_flag
        ):
            result.must_not_flag_hits.append(f_index)

    result.missed = [i for i in range(len(case.expected_findings)) if i not in matched_expected]
    result.located = sorted(located_expected)
    return result
