"""Command line of the evaluation. Run from backend/: `uv run python -m evals --help`."""

import argparse
import asyncio
import json
import logging
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import structlog

from evals.dataset import EVAL_DIR, load_cases, validate_case

BASELINE_PATH = EVAL_DIR / "baseline.json"
DEFAULT_MAX_F1_DROP = 0.03


def _load(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _save(document: dict[str, Any], out_dir: Path, compare: dict[str, Any] | None) -> Path:
    from evals.report import render_report

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{document['run']['id']}.json"
    path.write_text(
        json.dumps(document, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    path.with_suffix(".md").write_text(
        render_report(document, compare).rstrip() + "\n", encoding="utf-8", newline="\n"
    )
    return path


def _select(args: argparse.Namespace) -> list[Any]:
    cases = load_cases(
        args.split,
        sources=set(args.source) if args.source else None,
        ids=set(args.case) if args.case else None,
        smoke=args.smoke,
    )
    if not cases:
        sys.exit("No case matches the selection.")
    return cases


def _filters(args: argparse.Namespace) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    if args.source:
        filters["source"] = sorted(args.source)
    if args.case:
        filters["case"] = sorted(args.case)
    if args.smoke:
        filters["smoke"] = True
    return filters


def cmd_run(args: argparse.Namespace) -> None:
    from app.config import settings
    from evals.runner import RunConfig, run_evaluation

    filters = _filters(args)
    if args.prune_cache and (args.split != "all" or filters):
        sys.exit("--prune-cache needs the whole dataset (--split all, no filters).")
    model = args.model or (
        settings.OLLAMA_MODEL if args.provider == "ollama" else settings.GEMINI_MODEL
    )
    cases = _select(args)
    config = RunConfig(
        provider=args.provider,
        model=model,
        split=args.split,
        cache_mode=args.cache,
        concurrency=args.concurrency,
        timeout_seconds=args.timeout,
        prompts_dir=str(Path(args.prompts_dir).resolve()) if args.prompts_dir else "",
        label=args.label,
        filters=filters,
    )
    # The pipeline logs every step: keep only warnings and errors on the console
    logging.getLogger().setLevel(logging.WARNING)
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING))
    print(f"Evaluating {len(cases)} case(s) with {model} ({args.provider}), cache '{args.cache}'")
    document = asyncio.run(run_evaluation(config, cases, prune_cache=args.prune_cache))
    compare = _load(args.compare) if args.compare else None
    path = _save(document, Path(args.out), compare)
    overall = document["metrics"]["all"]["overall"]
    print(
        f"Precision {overall['precision']}, recall {overall['recall']}, F1 {overall['f1']}. "
        f"Results: {path} (+ .md report)"
    )
    if document["metrics"]["all"]["cases_failed"]:
        sys.exit(1)


def cmd_semgrep(args: argparse.Namespace) -> None:
    from evals.semgrep_baseline import run_semgrep

    cases = _select(args)
    document = run_semgrep(cases, args.split, _filters(args), config=args.config)
    path = _save(document, Path(args.out), None)
    overall = document["metrics"]["all"]["overall"]
    print(
        f"semgrep: precision {overall['precision']}, recall {overall['recall']}, "
        f"F1 {overall['f1']}. Results: {path}"
    )


def cmd_report(args: argparse.Namespace) -> None:
    from app.graph.synthesis import determine_verdict
    from evals.runner import build_document

    document = _load(args.results)
    # Recompute verdicts and metrics: the verdict and matching rules may have changed since
    # the run, and they only depend on the recorded findings
    for result in document["cases"]:
        if result["status"] != "ok":
            continue
        verdict = determine_verdict(result["findings"])
        if result.get("agent_errors") and verdict == "approve":
            verdict = "comment"  # a partial review never approves, as in synthesis
        result["verdict"] = verdict
    document = build_document(document["run"], document["cases"])
    compare = _load(args.compare) if args.compare else None
    path = _save(document, Path(args.results).parent, compare)
    print(f"Report written to {path.with_suffix('.md')}")


def cmd_check(args: argparse.Namespace) -> None:
    cases = load_cases("all")
    failures = 0
    for case in cases:
        for problem in validate_case(case):
            failures += 1
            print(f"{case.id}: {problem}")
    ids = Counter(case.id for case in cases)
    print(f"{len(cases)} cases, {failures} problem(s)")
    for key in ("split", "source", "language"):
        counts = Counter(str(getattr(case, key)) for case in cases)
        print(f"  by {key}: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    categories = Counter(e.category for case in cases for e in case.expected_findings)
    print("  expected findings: " + ", ".join(f"{k} {v}" for k, v in sorted(categories.items())))
    print(f"  smoke subset: {sum(case.smoke for case in cases)} cases")
    if failures or len(ids) != len(cases):
        sys.exit(1)


SOURCES_HEADER = """# Dataset sources

Generated by `uv run python -m evals sources` from the `case.yaml` files: do not edit by hand.

## Synthetic cases

Written for this project and released under the repository license (MIT). File names,
titles and code are realistic on purpose and contain no hint about the expected findings.

## Real-world cases

Files under `before/` and `after/` of these cases are copied from the listed open source
projects and keep their original license; the repository license does not apply to them.
Only projects with permissive licenses are included. CVE cases reverse the upstream
security fix: `after/` holds the vulnerable code.
"""


def cmd_sources(args: argparse.Namespace) -> None:
    cases = load_cases("all")
    lines = [SOURCES_HEADER]
    synthetic = [c for c in cases if c.source == "synthetic"]
    lines.append(f"Synthetic cases: {len(synthetic)}.\n")
    for source, title in (
        ("cve", "Reversed security fixes"),
        ("oss", "Merged pull requests (clean)"),
    ):
        selected = [c for c in cases if c.source == source]
        lines += [f"### {title} ({len(selected)})", ""]
        lines.append("| Case | Project | Change | Advisory | License |")
        lines.append("|---|---|---|---|---|")
        for case in selected:
            assert case.origin is not None  # noqa: S101 (enforced by the Case model)
            origin = case.origin
            advisory = " ".join(x for x in (origin.cve, origin.advisory) if x) or "-"
            lines.append(
                f"| `{case.id}` | [{origin.repo}](https://github.com/{origin.repo}) "
                f"| [link]({origin.url}) | {advisory} | {origin.license} |"
            )
        lines.append("")
    path = EVAL_DIR / "dataset" / "SOURCES.md"
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"Written {path}")


def cmd_gate(args: argparse.Namespace) -> None:
    """Fail when the F1 of a run drops more than the allowed margin below the baseline."""
    document = _load(args.results)
    baseline = _load(args.baseline)
    metrics = document["metrics"]["all"]
    problems = []
    if metrics["cases_failed"]:
        problems.append(
            f"{metrics['cases_failed']} case(s) could not be evaluated. If the prompts changed, "
            "record new answers locally (`uv run python -m evals run --smoke`) and commit "
            "eval/cache."
        )
    if document["run"]["dataset_fingerprint"] != baseline["dataset_fingerprint"]:
        problems.append(
            "The smoke dataset changed: update the baseline "
            "(`uv run python -m evals baseline <results.json>`)."
        )
    f1 = metrics["overall"]["f1"] or 0.0
    floor = baseline["metrics"]["f1"] - baseline.get("max_f1_drop", DEFAULT_MAX_F1_DROP)
    print(
        f"F1 {f1:.3f} (baseline {baseline['metrics']['f1']:.3f}, minimum {floor:.3f}); "
        f"precision {metrics['overall']['precision']}, recall {metrics['overall']['recall']}"
    )
    if f1 < floor - 1e-9:
        problems.append(f"F1 dropped below the baseline: {f1:.3f} < {floor:.3f}")
    for problem in problems:
        print(f"FAIL: {problem}")
    if problems:
        sys.exit(1)
    print("Regression gate passed.")


def cmd_baseline(args: argparse.Namespace) -> None:
    document = _load(args.results)
    metrics = document["metrics"]["all"]
    baseline = {
        "run_id": document["run"]["id"],
        "model": document["run"]["model"],
        "prompt_versions": document["run"]["prompt_versions"],
        "dataset_fingerprint": document["run"]["dataset_fingerprint"],
        "max_f1_drop": args.max_f1_drop,
        "metrics": {
            "precision": metrics["overall"]["precision"],
            "recall": metrics["overall"]["recall"],
            "f1": metrics["overall"]["f1"],
            "clean_flagged_rate": metrics["clean_flagged_rate"],
        },
    }
    BASELINE_PATH.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Baseline written to {BASELINE_PATH}")


def cmd_fetch(args: argparse.Namespace) -> None:
    from evals.github_fetch import fetch_commit_case, fetch_pr_case

    if args.kind == "commit":
        path = fetch_commit_case(
            args.repo, args.ref, args.id, reverse=args.reverse, paths=args.path
        )
    else:
        path = fetch_pr_case(args.repo, int(args.ref), args.id, paths=args.path)
    print(f"Case files written to {path}: complete case.yaml before using it.")


def _selection_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--split", choices=("dev", "test", "all"), default="dev")
    parser.add_argument("--source", action="append", choices=("synthetic", "cve", "oss"))
    parser.add_argument("--case", action="append", help="case id (repeatable)")
    parser.add_argument("--smoke", action="store_true", help="only the CI smoke subset")
    parser.add_argument("--out", default=str(EVAL_DIR / "results"))


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m evals", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="run the pipeline on the dataset")
    _selection_arguments(run)
    run.add_argument("--provider", choices=("ollama", "gemini"), default="ollama")
    run.add_argument("--model", help="defaults to the model configured for the provider")
    run.add_argument(
        "--cache",
        choices=("use", "replay", "refresh", "off"),
        default="use",
        help="use: replay recorded answers, record new ones; replay: fail on a missing answer; "
        "refresh: always call the model; off: no recording",
    )
    run.add_argument("--concurrency", type=int, default=1, help="cases run in parallel")
    run.add_argument("--timeout", type=float, default=600.0, help="seconds per LLM call")
    run.add_argument("--prompts-dir", help="evaluate an alternative prompt directory")
    run.add_argument("--label", default="", help="name of the run in the results file")
    run.add_argument("--compare", help="results file to compare with in the report")
    run.add_argument("--prune-cache", action="store_true", help="delete unused cached answers")
    run.set_defaults(func=cmd_run)

    semgrep = commands.add_parser("semgrep", help="baseline: semgrep alone on the same cases")
    _selection_arguments(semgrep)
    semgrep.add_argument("--config", default="p/default", help="semgrep rule set")
    semgrep.set_defaults(func=cmd_semgrep)

    report = commands.add_parser("report", help="recompute metrics and report of a results file")
    report.add_argument("results")
    report.add_argument("--compare", help="results file to compare with")
    report.set_defaults(func=cmd_report)

    check = commands.add_parser("check", help="validate the dataset")
    check.set_defaults(func=cmd_check)

    sources = commands.add_parser("sources", help="regenerate eval/dataset/SOURCES.md")
    sources.set_defaults(func=cmd_sources)

    gate = commands.add_parser("gate", help="CI regression gate on the F1 of a run")
    gate.add_argument("results")
    gate.add_argument("--baseline", default=str(BASELINE_PATH))
    gate.set_defaults(func=cmd_gate)

    baseline = commands.add_parser("baseline", help="save a smoke run as the CI baseline")
    baseline.add_argument("results")
    baseline.add_argument("--max-f1-drop", type=float, default=DEFAULT_MAX_F1_DROP)
    baseline.set_defaults(func=cmd_baseline)

    fetch = commands.add_parser("fetch", help="create a case from a GitHub commit or pull request")
    fetch.add_argument("kind", choices=("commit", "pr"))
    fetch.add_argument("repo", help="owner/name")
    fetch.add_argument("ref", help="commit sha or pull request number")
    fetch.add_argument("id", help="id of the new case")
    fetch.add_argument("--path", action="append", help="only these files (repeatable)")
    fetch.add_argument(
        "--reverse",
        action="store_true",
        help="swap before and after: a security fix becomes the change that introduces the bug",
    )
    fetch.set_defaults(func=cmd_fetch)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
