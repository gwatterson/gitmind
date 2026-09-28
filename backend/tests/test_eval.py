"""Evaluation framework: dataset loading, matching, metrics, report and diff tooling."""

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from app.diff.parser import parse_patch
from evals.dataset import Case, build_files, load_case, load_cases, make_patch, validate_case
from evals.github_fetch import PatchMismatchError, split_diff, unapply
from evals.matching import match_case
from evals.metrics import compute_metrics
from evals.report import render_report

BEFORE = "def load(conn, uid):\n    return conn.execute('SELECT 1')\n"
AFTER = (
    "def load(conn, uid):\n"
    "    return conn.execute('SELECT 1')\n"
    "\n"
    "\n"
    "def search(conn, term):\n"
    "    query = f\"SELECT * FROM users WHERE name = '{term}'\"\n"
    "    return conn.execute(query).fetchall()\n"
    "\n"
    "\n"
    "def count(conn):\n"
    "    return conn.execute('SELECT COUNT(*) FROM users WHERE active = ?', (1,))\n"
)


def write_case(root: Path, case_id: str = "sqli", **overrides: Any) -> Path:
    directory = root / case_id
    (directory / "before" / "app").mkdir(parents=True)
    (directory / "after" / "app").mkdir(parents=True)
    (directory / "before" / "app" / "db.py").write_text(BEFORE, encoding="utf-8")
    (directory / "after" / "app" / "db.py").write_text(AFTER, encoding="utf-8")
    data: dict[str, Any] = {
        "id": case_id,
        "split": "dev",
        "source": "synthetic",
        "language": "python",
        "title": "Add search",
        "description": "SQL injection in search",
        "expected_findings": [
            {
                "file": "app/db.py",
                "anchor": 'query = f"SELECT',
                "span": 1,
                "category": "security",
                "cwe": "CWE-89",
                "severity_min": "high",
                "description": "SQL injection",
            }
        ],
        "must_not_flag": [
            {"file": "app/db.py", "anchor": "SELECT COUNT(*)", "reason": "parameterized"}
        ],
    }
    data.update(overrides)
    (directory / "case.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    return directory


def finding(line: int, category: str = "security", **extra: Any) -> dict[str, Any]:
    return {
        "file": "app/db.py",
        "line": line,
        "severity": "high",
        "category": category,
        "rule_id": "rule",
        "cwe": "CWE-89",
        "confidence": 0.9,
        "agent": category,
        "message": "problem",
        **extra,
    }


@pytest.fixture
def case(tmp_path: Path) -> Case:
    return load_case(write_case(tmp_path))


# --- Dataset -----------------------------------------------------------------


def test_patch_matches_the_github_format():
    patch = make_patch(BEFORE.splitlines(), AFTER.splitlines())
    assert patch.startswith("@@ -1,2 +1,11 @@")
    parsed = parse_patch(patch)
    assert parsed.added_lines == set(range(3, 12))


def test_case_files_are_diffed_with_line_counts(case: Case):
    [file] = case.files
    assert file["filename"] == "app/db.py"
    assert file["language"] == "python"
    assert (file["additions"], file["deletions"]) == (9, 0)


def test_new_files_have_no_before_version(tmp_path: Path):
    directory = write_case(tmp_path)
    (directory / "after" / "app" / "new.py").write_text("x = 1\n", encoding="utf-8")
    names = {f["filename"]: f for f in build_files(directory)}
    assert names["app/new.py"]["patch"].startswith("@@ -0,0 +1 @@")


def test_anchors_are_resolved_to_line_numbers(case: Case):
    assert case.expected_findings[0].lines == (6, 7)
    assert case.must_not_flag[0].lines == (11, 11)
    assert validate_case(case) == []


@pytest.mark.parametrize("anchor", ["conn.execute", "not in the file"])
def test_ambiguous_or_missing_anchors_are_rejected(tmp_path: Path, anchor: str):
    directory = write_case(
        tmp_path,
        expected_findings=[
            {
                "file": "app/db.py",
                "anchor": anchor,
                "category": "security",
                "description": "x",
            }
        ],
    )
    with pytest.raises(ValueError, match="anchor"):
        load_case(directory)


def test_ranges_outside_the_diff_are_reported(tmp_path: Path):
    directory = write_case(
        tmp_path,
        must_not_flag=[
            {"file": "app/db.py", "lines": 30, "reason": "past the end"},
            {"file": "app/other.py", "lines": 1, "reason": "not changed"},
        ],
    )
    problems = validate_case(load_case(directory))
    assert problems == [
        "must_not_flag app/db.py:(30, 30): no line of the range is in the diff",
        "must_not_flag app/other.py:(1, 1): file not in the diff",
    ]


def test_case_consistency_rules():
    base = {
        "id": "x",
        "split": "dev",
        "language": "python",
        "title": "t",
        "description": "d",
    }
    with pytest.raises(ValidationError, match="clean cases"):
        Case.model_validate(
            {
                **base,
                "source": "oss",
                "origin": {"repo": "a/b", "url": "u", "license": "MIT"},
                "expected_findings": [
                    {"file": "f", "lines": 1, "category": "quality", "description": "d"}
                ],
            }
        )
    with pytest.raises(ValidationError, match="expected finding"):
        Case.model_validate(
            {**base, "source": "cve", "origin": {"repo": "a/b", "url": "u", "license": "MIT"}}
        )
    with pytest.raises(ValidationError, match="origin"):
        Case.model_validate({**base, "source": "oss"})
    clean = Case.model_validate({**base, "source": "synthetic"})
    assert clean.is_clean and not clean.expects_block


def test_load_cases_filters_by_split_and_id(tmp_path: Path):
    write_case(tmp_path, "one")
    write_case(tmp_path, "two", split="test", smoke=True)
    assert [c.id for c in load_cases("dev", cases_dir=tmp_path)] == ["one"]
    assert [c.id for c in load_cases("all", smoke=True, cases_dir=tmp_path)] == ["two"]
    assert [c.id for c in load_cases("all", ids={"one"}, cases_dir=tmp_path)] == ["one"]


# --- Matching ------------------------------------------------------------------


def test_finding_inside_the_range_matches(case: Case):
    result = match_case(case, [finding(6)])
    assert [(m.distance, m.cwe_ok, m.severity_ok) for m in result.matches] == [(0, True, True)]
    assert result.false_positives == [] and result.missed == []


def test_line_tolerance_is_three_lines(case: Case):
    assert match_case(case, [finding(10)]).matches[0].distance == 3
    assert match_case(case, [finding(2)]).false_positives == [0]


def test_wrong_category_is_located_but_not_matched(case: Case):
    result = match_case(case, [finding(6, category="quality")])
    assert result.matches == [] and result.false_positives == [0]
    assert result.located == [0]


def test_second_finding_on_the_same_problem_is_a_duplicate(case: Case):
    result = match_case(case, [finding(9), finding(6, cwe="CWE-20", severity="low")])
    assert [m.finding for m in result.matches] == [1]  # the closest one
    assert result.matches[0].cwe_ok is False and result.matches[0].severity_ok is False
    assert result.duplicates == [0]


def test_must_not_flag_and_unplaced_findings(case: Case):
    result = match_case(case, [finding(11), finding(0), finding(6)])
    assert result.must_not_flag_hits == [0]
    assert result.unplaced == [1]
    assert result.false_positives == [0, 1]


# --- Metrics and report -------------------------------------------------------


def result_for(case: Case, findings: list[dict[str, Any]], verdict: str, **extra: Any) -> dict:
    return {
        "case": case.model_dump(mode="json"),
        "status": "ok",
        "error": None,
        "agent_errors": [],
        "verdict": verdict,
        "findings": findings,
        "wall_seconds": 10.0,
        "stats": {"live_calls": 3, "cached_calls": 0, "llm_seconds": 9.0},
        **extra,
    }


@pytest.fixture
def results(tmp_path: Path, case: Case) -> list[dict]:
    clean_dir = write_case(tmp_path, "clean", expected_findings=[])
    clean = load_case(clean_dir)
    return [
        result_for(case, [finding(6), finding(11, category="quality", severity="low")], "comment"),
        result_for(clean, [finding(3, severity="high")], "request_changes"),
    ]


def test_metrics_count_true_and_false_positives(results):
    metrics = compute_metrics(results).to_dict()
    assert metrics["overall"] == {
        "tp": 1,
        "fp": 2,
        "expected": 1,
        "found": 1,
        "precision": 0.333,
        "recall": 1.0,
        "f1": 0.5,
    }
    assert metrics["clean_flagged_rate"] == 1.0
    assert metrics["clean_blocked_rate"] == 1.0
    assert metrics["blocking_recall"] == 0.0  # the vulnerable case only got a comment
    assert metrics["must_not_flag_hits"] == 1
    assert metrics["by_category"]["quality"]["fp"] == 1
    assert metrics["latency"]["live_cases"] == 2


def test_severity_threshold_drops_low_findings(results):
    metrics = compute_metrics(results, "medium").to_dict()
    assert metrics["overall"]["fp"] == 1
    assert metrics["must_not_flag_hits"] == 0


def test_failed_cases_are_excluded_and_counted(results):
    results[1]["status"] = "error"
    metrics = compute_metrics(results).to_dict()
    assert metrics["cases_failed"] == 1
    assert metrics["clean_cases"] == 0


def test_report_renders_headline_and_comparison(results):
    run = {
        "id": "run-1",
        "pipeline": "gitmind",
        "provider": "ollama",
        "model": "qwen",
        "split": "dev",
        "cases": 2,
        "dataset_fingerprint": "abc",
        "prompt_versions": "security@1",
        "code_revision": "123",
        "cache_mode": "use",
        "line_tolerance": 3,
    }
    document = {
        "run": run,
        "metrics": {
            "all": compute_metrics(results).to_dict(),
            "medium_plus": compute_metrics(results, "medium").to_dict(),
        },
        "cases": results,
    }
    other = json.loads(json.dumps(document))
    other["run"] = {**run, "id": "run-0", "pipeline": "semgrep", "model": "1.0"}
    other["metrics"]["all"]["overall"]["f1"] = 0.25
    report = render_report(document, other)
    assert "| F1 | 0.50 | 0.67 | 0.25 | +0.25 |" in report
    assert "`sqli`" in report and "`clean`" in report
    assert "semgrep (1.0)" in report


# --- GitHub diff tooling -----------------------------------------------------


def git_diff(name: str, before: str, after: str) -> str:
    patch = make_patch(before.splitlines(), after.splitlines())
    return f"diff --git a/{name} b/{name}\nindex 1..2 100644\n--- a/{name}\n+++ b/{name}\n{patch}\n"


def test_unapply_rebuilds_the_old_version():
    before = "\n".join(f"line {i}" for i in range(1, 30))
    after = before.replace("line 3", "line three").replace("line 20\n", "") + "\nline 30"
    [file] = split_diff(git_diff("a.py", before, after))
    assert (file.old_path, file.new_path) == ("a.py", "a.py")
    assert unapply(after.splitlines(), file.patch) == before.splitlines()


def test_unapply_handles_added_and_deleted_files():
    diff = (
        "diff --git a/old.py b/old.py\ndeleted file mode 100644\n--- a/old.py\n+++ /dev/null\n"
        "@@ -1,2 +0,0 @@\n-a\n-b\n"
        "diff --git a/new.py b/new.py\nnew file mode 100644\n--- /dev/null\n+++ b/new.py\n"
        "@@ -0,0 +1 @@\n+c\n"
    )
    deleted, added = split_diff(diff)
    assert (deleted.old_path, deleted.new_path) == ("old.py", None)
    assert unapply([], deleted.patch) == ["a", "b"]
    assert (added.old_path, added.new_path) == (None, "new.py")


def test_unapply_detects_content_that_does_not_match_the_diff():
    [file] = split_diff(git_diff("a.py", "x\ny\n", "x\nz\n"))
    with pytest.raises(PatchMismatchError):
        unapply(["x", "something else"], file.patch)


def test_alternative_locations_of_the_same_problem(tmp_path: Path):
    directory = write_case(
        tmp_path,
        expected_findings=[
            {
                "file": "app/db.py",
                "anchor": 'query = f"SELECT',
                "category": "security",
                "description": "SQL injection",
                "also": [{"file": "app/db.py", "anchor": "return conn.execute(query)"}],
            }
        ],
        must_not_flag=[],
    )
    case = load_case(directory)
    assert case.expected_findings[0].also[0].lines == (7, 7)
    result = match_case(case, [finding(7), finding(6)])
    assert [m.finding for m in result.matches] == [0]
    assert result.duplicates == [1]
    assert result.false_positives == []
