"""Markdown report of an evaluation run, optionally compared with another run."""

from typing import Any

from evals.dataset import Case
from evals.matching import match_case

HEADLINE = (
    ("Precision", ("overall", "precision")),
    ("Recall", ("overall", "recall")),
    ("F1", ("overall", "f1")),
    ("Localization recall (any category)", ("localization_recall",)),
    ("Line inside expected range", ("line_exact_rate",)),
    ("CWE accuracy (matched security findings)", ("cwe_accuracy",)),
    ("Clean PRs with at least one finding", ("clean_flagged_rate",)),
    ("Findings per clean PR", ("findings_per_clean_case",)),
    ("Unsafe PRs blocked (request changes)", ("blocking_recall",)),
    ("Clean PRs blocked", ("clean_blocked_rate",)),
    ("Findings on must-not-flag lines", ("must_not_flag_hits",)),
)


def _get(metrics: dict[str, Any], path: tuple[str, ...]) -> Any:
    value: Any = metrics
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".") if value > 1 else f"{value:.2f}"
    return str(value)


def _delta(value: Any, other: Any) -> str:
    if not isinstance(value, int | float) or not isinstance(other, int | float):
        return ""
    diff = value - other
    if abs(diff) < 1e-9:
        return "="
    return f"{diff:+.2f}" if isinstance(diff, float) else f"{diff:+d}"


def _table(rows: list[list[str]], header: list[str]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return lines


def _counts_table(groups: dict[str, dict[str, Any]], title: str) -> list[str]:
    rows = [
        [
            name,
            str(c["expected"]),
            str(c["found"]),
            str(c["fp"]),
            _fmt(c["precision"]),
            _fmt(c["recall"]),
            _fmt(c["f1"]),
        ]
        for name, c in groups.items()
    ]
    return _table(rows, [title, "Expected", "Found", "False pos.", "Precision", "Recall", "F1"])


def describe_run(run: dict[str, Any]) -> str:
    if run["pipeline"] == "semgrep":
        return f"semgrep ({run['model']})"
    return f"GitMind with {run['model']} ({run['provider']})"


def render_report(document: dict[str, Any], compare: dict[str, Any] | None = None) -> str:
    run = document["run"]
    metrics = document["metrics"]
    lines = [
        f"# Evaluation run {run['id']}",
        "",
        f"- Pipeline: {describe_run(run)}",
        f"- Split: `{run['split']}`, {run['cases']} cases, dataset `{run['dataset_fingerprint']}`"
        + (f", filters {run['filters']}" if run.get("filters") else ""),
    ]
    if run.get("prompt_versions"):
        lines.append(f"- Prompts: `{run['prompt_versions']}`")
    lines += [
        f"- Code revision: `{run['code_revision']}`, cache mode `{run['cache_mode']}`",
        f"- Matching: same file and category, line within {run['line_tolerance']} of the expected range",
    ]
    if compare:
        lines.append(
            f"- Compared with: {describe_run(compare['run'])}, run `{compare['run']['id']}`"
        )
    lines.append("")

    all_metrics, medium = metrics["all"], metrics["medium_plus"]
    if all_metrics["cases_failed"] or all_metrics["cases_with_agent_errors"]:
        lines += [
            f"> {all_metrics['cases_failed']} case(s) failed and "
            f"{all_metrics['cases_with_agent_errors']} had agent errors: see the case table.",
            "",
        ]

    header = ["Metric", "All findings", "Severity >= medium"]
    if compare:
        header += ["Compared run (all)", "Delta"]
    rows = []
    for name, path in HEADLINE:
        value = _get(all_metrics, path)
        row = [name, _fmt(value), _fmt(_get(medium, path))]
        if compare:
            other = _get(compare["metrics"]["all"], path)
            row += [_fmt(other), _delta(value, other)]
        rows.append(row)
    lines += ["## Headline", "", *_table(rows, header), ""]

    lines += ["## By category", "", *_counts_table(all_metrics["by_category"], "Category"), ""]
    lines += ["## By source", "", *_counts_table(all_metrics["by_source"], "Source"), ""]
    lines += ["## By language", "", *_counts_table(all_metrics["by_language"], "Language"), ""]

    latency, usage = all_metrics["latency"], all_metrics["usage"]
    lines += [
        "## Cost and latency",
        "",
        *_table(
            [
                ["Cases measured live", str(latency["live_cases"])],
                [
                    "Wall time per review p50 / p95 (s)",
                    f"{_fmt(latency['wall_p50'])} / {_fmt(latency['wall_p95'])}",
                ],
                ["LLM calls per review", _fmt(usage["calls_per_case"])],
                [
                    "Input / output tokens per review",
                    f"{_fmt(usage['input_tokens_per_case'])} / {_fmt(usage['output_tokens_per_case'])}",
                ],
                ["Live / replayed calls", f"{usage['live_calls']} / {usage['cached_calls']}"],
            ],
            ["", "Value"],
        ),
        "",
    ]

    rows = []
    for result in document["cases"]:
        case = result["case"]
        matched = match_case(Case.model_validate(case), result["findings"])
        rows.append(
            [
                f"`{case['id']}`",
                case["source"],
                f"{len(matched.matches)}/{len(case['expected_findings'])}",
                str(len(matched.false_positives)),
                result["verdict"] or "-",
                result["status"] if not result["agent_errors"] else "agent errors",
            ]
        )
    lines += [
        "## Cases",
        "",
        *_table(rows, ["Case", "Source", "Found", "False pos.", "Verdict", "Status"]),
        "",
    ]
    return "\n".join(lines)
