"""Baseline: semgrep alone on the same cases, scored with the same matching rules.

semgrep scans the full files after the change (after/), and only results on lines
the pull request shows (the lines GitMind can comment on) are kept, like a
diff-aware CI scan. semgrep runs from PATH when installed, otherwise from its
Docker image (semgrep has no native Windows build).
"""

import json
import re
import shutil
import subprocess
import tempfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.diff.parser import parse_patch
from app.graph.synthesis import determine_verdict
from evals.dataset import Case, dataset_fingerprint
from evals.matching import LINE_TOLERANCE
from evals.runner import build_document, git_revision

DOCKER_IMAGE = "semgrep/semgrep:latest"

_SEVERITY = {"ERROR": "high", "WARNING": "medium", "INFO": "low"}
_CONFIDENCE = {"HIGH": 0.9, "MEDIUM": 0.6, "LOW": 0.3}
_CWE = re.compile(r"CWE-(\d+)")


def _command(target: Path, config: str) -> list[str]:
    args = ["scan", "--config", config, "--json", "--metrics", "off", "--quiet"]
    if shutil.which("semgrep"):
        return ["semgrep", *args, str(target)]
    return [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{target.resolve()}:/src",
        DOCKER_IMAGE,
        "semgrep",
        *args,
        "/src",
    ]


def _category(metadata: dict[str, Any]) -> str:
    category = str(metadata.get("category", "")).lower()
    if category == "security":
        return "security"
    if category == "performance":
        return "performance"
    return "quality"


def _cwe(metadata: dict[str, Any]) -> str | None:
    values = metadata.get("cwe") or []
    for value in values if isinstance(values, list) else [values]:
        match = _CWE.search(str(value))
        if match:
            return f"CWE-{match.group(1)}"
    return None


def to_finding(result: dict[str, Any], filename: str) -> dict[str, Any]:
    extra = result.get("extra", {})
    metadata = extra.get("metadata", {})
    category = _category(metadata)
    return {
        "file": filename,
        "line": int(result["start"]["line"]),
        "severity": _SEVERITY.get(str(extra.get("severity", "")).upper(), "low"),
        "category": category,
        "rule_id": str(result.get("check_id", "")).rsplit(".", 1)[-1],
        "cwe": _cwe(metadata) if category == "security" else None,
        "confidence": _CONFIDENCE.get(str(metadata.get("confidence", "")).upper(), 0.6),
        "agent": "semgrep",
        "message": str(extra.get("message", ""))[:400],
        "evidence": str(extra.get("lines", ""))[:300],
    }


def _version() -> str:
    command = _command(Path("."), "")
    command = [*command[: command.index("scan")], "--version"]
    try:
        return subprocess.run(command, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def run_semgrep(
    cases: list[Case], split: str, filters: dict[str, Any], *, config: str = "p/default"
) -> dict[str, Any]:
    """Scan every case in one semgrep run and score it like a GitMind run."""
    with tempfile.TemporaryDirectory(prefix="gitmind-semgrep-") as tmp:
        root = Path(tmp)
        for case in cases:
            assert case.directory is not None  # noqa: S101 (set by the loader)
            after = case.directory / "after"
            if after.is_dir():
                shutil.copytree(after, root / case.id)
        completed = subprocess.run(
            _command(root, config), capture_output=True, text=True, encoding="utf-8", check=False
        )
    if completed.returncode not in (0, 1):  # 1: findings were reported
        raise RuntimeError(f"semgrep failed ({completed.returncode}): {completed.stderr[-2000:]}")
    output = json.loads(completed.stdout)

    by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in output.get("results", []):
        path = Path(result["path"]).as_posix()
        parts = path.split("/")
        # Paths are relative to the scanned root, possibly with the /src mount prefix
        while parts and parts[0] in ("", "src", ".", root.as_posix().lstrip("/")):
            parts = parts[1:]
        if len(parts) < 2:
            continue
        by_case[parts[0]].append({**result, "_file": "/".join(parts[1:])})

    results = []
    for case in cases:
        commentable = {f["filename"]: parse_patch(f["patch"]).commentable_lines for f in case.files}
        findings = [
            to_finding(raw, raw["_file"])
            for raw in by_case.get(case.id, [])
            if int(raw["start"]["line"]) in commentable.get(raw["_file"], set())
        ]
        results.append(
            {
                "case": case.model_dump(mode="json"),
                "status": "ok",
                "error": None,
                "agent_errors": [],
                "verdict": determine_verdict(findings),  # type: ignore[arg-type]
                "findings": findings,
                "files": [f["filename"] for f in case.files],
                "wall_seconds": 0.0,
                "stats": {},
            }
        )

    created = datetime.now(UTC)
    meta = {
        "id": f"{created:%Y%m%d-%H%M%S}-semgrep",
        "label": "semgrep",
        "created_at": created.isoformat(timespec="seconds"),
        "pipeline": "semgrep",
        "provider": "semgrep",
        "model": f"{_version()}, {config}",
        "prompt_versions": None,
        "prompts": None,
        "prompts_dir": None,
        "split": split,
        "filters": filters,
        "cases": len(cases),
        "dataset_fingerprint": dataset_fingerprint(cases),
        "code_revision": git_revision(),
        "cache_mode": "off",
        "line_tolerance": LINE_TOLERANCE,
        "semgrep_errors": len(output.get("errors", [])),
    }
    return build_document(meta, results)
