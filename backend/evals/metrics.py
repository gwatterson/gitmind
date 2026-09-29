"""Aggregate metrics of an evaluation run.

Everything is computed from the saved results (cases, findings, call stats), so a
report can be regenerated, or recomputed with another severity threshold, without
calling the model again.
"""

import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any

from app.graph.state import Finding
from app.graph.synthesis import deduplicate_findings
from app.graph.taxonomy import assign_owner_category
from evals.dataset import SEVERITY_RANK, Case
from evals.matching import match_case


@dataclass
class Counts:
    tp: int = 0  # findings matching an expected finding
    fp: int = 0
    expected: int = 0
    found: int = 0  # expected findings matched by a finding

    @property
    def precision(self) -> float | None:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else None

    @property
    def recall(self) -> float | None:
        return self.found / self.expected if self.expected else None

    @property
    def f1(self) -> float | None:
        p, r = self.precision, self.recall
        if p is None or r is None or p + r == 0:
            return None if p is None or r is None else 0.0
        return 2 * p * r / (p + r)

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "precision": _round(self.precision),
            "recall": _round(self.recall),
            "f1": _round(self.f1),
        }


def _round(value: float | None, digits: int = 3) -> float | None:
    return None if value is None else round(value, digits)


def _ratio(numerator: int, denominator: int) -> float | None:
    return _round(numerator / denominator) if denominator else None


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return round(values[0], 2)
    return round(statistics.quantiles(values, n=100, method="inclusive")[int(q) - 1], 2)


@dataclass
class Metrics:
    min_severity: str
    cases: int = 0
    cases_failed: int = 0  # the run crashed or could not replay the case
    cases_with_agent_errors: int = 0
    overall: Counts = field(default_factory=Counts)
    by_category: dict[str, Counts] = field(default_factory=lambda: defaultdict(Counts))
    by_language: dict[str, Counts] = field(default_factory=lambda: defaultdict(Counts))
    by_source: dict[str, Counts] = field(default_factory=lambda: defaultdict(Counts))
    located: int = 0  # expected findings with a finding at the right place, any category
    line_distances: list[int] = field(default_factory=list)
    cwe_checked: int = 0
    cwe_correct: int = 0
    severity_ok: int = 0
    duplicates: int = 0
    unplaced: int = 0
    must_not_flag: int = 0
    must_not_flag_hits: int = 0
    clean_cases: int = 0
    clean_cases_flagged: int = 0
    clean_findings: int = 0
    block_expected: int = 0
    block_expected_blocked: int = 0
    clean_blocked: int = 0
    wall_seconds: list[float] = field(default_factory=list)  # live cases only
    llm_seconds: list[float] = field(default_factory=list)
    calls: list[int] = field(default_factory=list)
    input_tokens: list[int] = field(default_factory=list)
    output_tokens: list[int] = field(default_factory=list)
    live_calls: int = 0
    cached_calls: int = 0

    def to_dict(self) -> dict[str, Any]:
        matched = len(self.line_distances)
        return {
            "min_severity": self.min_severity,
            "cases": self.cases,
            "cases_failed": self.cases_failed,
            "cases_with_agent_errors": self.cases_with_agent_errors,
            "overall": self.overall.to_dict(),
            "by_category": {k: v.to_dict() for k, v in sorted(self.by_category.items())},
            "by_language": {k: v.to_dict() for k, v in sorted(self.by_language.items())},
            "by_source": {k: v.to_dict() for k, v in sorted(self.by_source.items())},
            "localization_recall": _ratio(self.located, self.overall.expected),
            "line_exact_rate": _ratio(sum(1 for d in self.line_distances if d == 0), matched),
            "mean_line_distance": _round(statistics.fmean(self.line_distances))
            if self.line_distances
            else None,
            "cwe_accuracy": _ratio(self.cwe_correct, self.cwe_checked),
            "severity_adequate_rate": _ratio(self.severity_ok, matched),
            "duplicates": self.duplicates,
            "unplaced_findings": self.unplaced,
            "must_not_flag": self.must_not_flag,
            "must_not_flag_hits": self.must_not_flag_hits,
            "clean_cases": self.clean_cases,
            "clean_flagged_rate": _ratio(self.clean_cases_flagged, self.clean_cases),
            "findings_per_clean_case": _round(self.clean_findings / self.clean_cases)
            if self.clean_cases
            else None,
            "blocking_recall": _ratio(self.block_expected_blocked, self.block_expected),
            "clean_blocked_rate": _ratio(self.clean_blocked, self.clean_cases),
            "latency": {
                "live_cases": len(self.wall_seconds),
                "wall_p50": _percentile(self.wall_seconds, 50),
                "wall_p95": _percentile(self.wall_seconds, 95),
                "llm_seconds_p50": _percentile(self.llm_seconds, 50),
                "llm_seconds_p95": _percentile(self.llm_seconds, 95),
            },
            "usage": {
                "calls_per_case": _round(statistics.fmean(self.calls)) if self.calls else None,
                "input_tokens_per_case": round(statistics.fmean(self.input_tokens))
                if self.input_tokens
                else None,
                "output_tokens_per_case": round(statistics.fmean(self.output_tokens))
                if self.output_tokens
                else None,
                "live_calls": self.live_calls,
                "cached_calls": self.cached_calls,
            },
        }


def filter_findings(findings: list[dict[str, Any]], min_severity: str) -> list[dict[str, Any]]:
    threshold = SEVERITY_RANK[min_severity]
    return [f for f in findings if SEVERITY_RANK.get(str(f.get("severity")), 0) >= threshold]


def compute_metrics(results: list[dict[str, Any]], min_severity: str = "info") -> Metrics:
    """Metrics over the case results of a run (see evals.runner.CaseResult)."""
    metrics = Metrics(min_severity=min_severity)
    for result in results:
        case = Case.model_validate(result["case"])
        metrics.cases += 1
        if result["status"] != "ok":
            metrics.cases_failed += 1
            continue
        if result.get("agent_errors"):
            metrics.cases_with_agent_errors += 1

        findings = filter_findings(result["findings"], min_severity)
        match = match_case(case, findings)
        groups = (
            metrics.overall,
            metrics.by_language[case.language],
            metrics.by_source[case.source],
        )
        for counts in groups:
            counts.tp += len(match.matches)
            counts.fp += len(match.false_positives)
            counts.expected += len(case.expected_findings)
            counts.found += len(match.matches)
        for expected in case.expected_findings:
            metrics.by_category[expected.category].expected += 1
        for m in match.matches:
            metrics.by_category[case.expected_findings[m.expected].category].found += 1
            metrics.by_category[str(findings[m.finding].get("category"))].tp += 1
            metrics.line_distances.append(m.distance)
            metrics.severity_ok += m.severity_ok
            if m.cwe_ok is not None:
                metrics.cwe_checked += 1
                metrics.cwe_correct += m.cwe_ok
        for index in match.false_positives:
            metrics.by_category[str(findings[index].get("category"))].fp += 1

        metrics.located += len(match.located)
        metrics.duplicates += len(match.duplicates)
        metrics.unplaced += len(match.unplaced)
        metrics.must_not_flag += len(case.must_not_flag)
        metrics.must_not_flag_hits += len(match.must_not_flag_hits)

        # The verdict is always computed on every finding, like in production
        blocked = result.get("verdict") == "request_changes"
        if case.is_clean:
            metrics.clean_cases += 1
            metrics.clean_findings += len(findings)
            metrics.clean_cases_flagged += bool(findings)
            metrics.clean_blocked += blocked
        elif case.expects_block:
            metrics.block_expected += 1
            metrics.block_expected_blocked += blocked

        stats = result.get("stats", {})
        if stats.get("live_calls") and not stats.get("cached_calls"):
            metrics.wall_seconds.append(float(result.get("wall_seconds", 0.0)))
        metrics.llm_seconds.append(float(stats.get("llm_seconds", 0.0)))
        metrics.calls.append(int(stats.get("live_calls", 0)) + int(stats.get("cached_calls", 0)))
        metrics.input_tokens.append(int(stats.get("input_tokens", 0)))
        metrics.output_tokens.append(int(stats.get("output_tokens", 0)))
        metrics.live_calls += int(stats.get("live_calls", 0))
        metrics.cached_calls += int(stats.get("cached_calls", 0))
    return metrics


VERIFIER_THRESHOLDS = (0.0, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)


def _as_findings(items: list[dict[str, Any]]) -> list[Finding]:
    return [Finding(**{"suggestion": "", "message": "", **item}) for item in items]  # type: ignore[typeddict-item]


def verifier_curve(
    results: list[dict[str, Any]], thresholds: tuple[float, ...] = VERIFIER_THRESHOLDS
) -> list[dict[str, Any]]:
    """Metrics as if the verifier had used each threshold, from the recorded candidates.

    Every candidate the verifier judged is in the results (kept or suppressed) with its
    confidence, so any threshold can be replayed without calling the model. Candidates are
    merged like the synthesis does: owner category, then duplicates.
    """
    if not any(result.get("suppressed") for result in results):
        return []
    curve = []
    for threshold in thresholds:
        replayed = []
        for result in results:
            candidates = [*result.get("findings", []), *result.get("suppressed", [])]
            passing = [
                c
                for c in candidates
                if c.get("verifier_confidence") is None
                or (c.get("verifier_real") is not False and c["verifier_confidence"] >= threshold)
            ]
            merged = deduplicate_findings([assign_owner_category(f) for f in _as_findings(passing)])
            replayed.append({**result, "findings": [dict(f) for f in merged]})
        metrics = compute_metrics(replayed).to_dict()
        curve.append(
            {
                "threshold": threshold,
                **{k: metrics["overall"][k] for k in ("precision", "recall", "f1")},
                "findings_per_clean_case": metrics["findings_per_clean_case"],
            }
        )
    return curve
