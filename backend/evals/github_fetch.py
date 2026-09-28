"""Create real-world cases from public GitHub commits and pull requests.

- A security fix fetched with reverse=True becomes the change that introduces the
  vulnerability: before/ holds the fixed code, after/ the vulnerable code.
- A merged pull request of a mature project becomes a clean case, used to
  measure false positives.

Only public web endpoints are used for the content (the `.diff` of the commit or
pull request and raw files): the version before the change is rebuilt by
applying the diff in reverse to the version after it, and checked line by line.
The REST API is called once per repository (license) and once per pull request
(head commit); set GITHUB_TOKEN to raise its limit of 60 requests per hour.

The generated case.yaml is a skeleton: expected findings must be written (or at
least checked) by hand.
"""

import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import yaml

from app.diff.files import detect_language
from app.diff.parser import parse_patch
from evals.dataset import CASES_DIR, build_files

API = "https://api.github.com"
WEB = "https://github.com"
RAW = "https://raw.githubusercontent.com"
MAX_FILE_BYTES = 300_000

# Files that do not belong in a code review case unless asked for explicitly
_SKIPPED_PARTS = ("test", "spec", "docs/", "changelog", "changes", "news", ".md", ".rst", ".txt")
_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


class PatchMismatchError(ValueError):
    """The file content does not match the diff it should come from."""


@dataclass
class FileDiff:
    old_path: str | None  # None for added files
    new_path: str | None  # None for deleted files
    patch: str  # from the first hunk header on


def split_diff(diff: str) -> list[FileDiff]:
    """Split a multi-file git diff into per-file patches."""
    files: list[FileDiff] = []
    old_path: str | None = None
    new_path: str | None = None
    body: list[str] | None = None

    def flush() -> None:
        if body is not None and (old_path or new_path):
            files.append(FileDiff(old_path, new_path, "\n".join(body)))

    for line in diff.splitlines():
        if line.startswith("diff --git "):
            flush()
            names = line[len("diff --git ") :]
            old_path = names.split(" b/", 1)[0].removeprefix("a/")
            new_path = names.split(" b/", 1)[-1]
            body = None
        elif body is None and line.startswith("--- "):
            old_path = None if line == "--- /dev/null" else line[4:].removeprefix("a/")
        elif body is None and line.startswith("+++ "):
            new_path = None if line == "+++ /dev/null" else line[4:].removeprefix("b/")
            body = []
        elif body is not None:
            body.append(line)
    flush()
    return files


def unapply(new_lines: list[str], patch: str) -> list[str]:
    """Rebuild the old version of a file from its new version and the patch between them."""
    old: list[str] = []
    position = 0  # index in new_lines
    for hunk in parse_patch(patch).hunks:
        match = _HUNK.match(hunk.header)
        if match is None:
            raise PatchMismatchError(f"bad hunk header {hunk.header!r}")
        # A hunk with no new lines ("+12,0") points at the line before the change
        new_start, new_count = int(match.group(3)), int(match.group(4) or 1)
        start = new_start - 1 if new_count else new_start
        old.extend(new_lines[position:start])
        position = start
        for line in hunk.lines:
            if line.kind == "del":
                old.append(line.content)
                continue
            if position >= len(new_lines) or new_lines[position] != line.content:
                raise PatchMismatchError(f"line {position + 1} differs from the diff")
            if line.kind == "ctx":
                old.append(line.content)
            position += 1
    old.extend(new_lines[position:])
    return old


def _client() -> httpx.Client:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "gitmind-eval"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(headers=headers, timeout=30, follow_redirects=True)


def _get(client: httpx.Client, url: str) -> httpx.Response:
    response = client.get(url)
    response.raise_for_status()
    return response


def _raw(client: httpx.Client, repo: str, ref: str, path: str) -> list[str]:
    response = _get(client, f"{RAW}/{repo}/{ref}/{path}")
    if len(response.content) > MAX_FILE_BYTES:
        raise ValueError(f"{path} is larger than {MAX_FILE_BYTES} bytes")
    return response.content.decode("utf-8").replace("\r\n", "\n").splitlines()


def _wanted(filename: str, paths: list[str] | None) -> bool:
    if paths:
        return filename in paths
    lowered = filename.lower()
    return detect_language(filename) != "unknown" and not any(p in lowered for p in _SKIPPED_PARTS)


def _write(directory: Path, side: str, name: str, lines: list[str] | None) -> None:
    if lines is None:
        return
    path = directory / side / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


_licenses: dict[str, str] = {}


def _license(client: httpx.Client, repo: str) -> str:
    """SPDX id of the repository license (NOASSERTION for custom licenses: check by hand)."""
    if repo not in _licenses:
        info = _get(client, f"{API}/repos/{repo}").json()
        license_info = info.get("license") or {}
        _licenses[repo] = str(license_info.get("spdx_id") or "unknown")
    return _licenses[repo]


def _materialize(
    client: httpx.Client,
    directory: Path,
    repo: str,
    ref: str,
    diff: str,
    *,
    reverse: bool,
    paths: list[str] | None,
) -> None:
    """Write before/ and after/ for the wanted files of a diff whose new side is `ref`."""
    written = 0
    for file in split_diff(diff):
        name = file.new_path or file.old_path
        if name is None or not _wanted(name, paths):
            continue
        new = _raw(client, repo, ref, file.new_path) if file.new_path else []
        old = unapply(new, file.patch) if file.old_path else None
        new_side = new if file.new_path else None
        before, after = (new_side, old) if reverse else (old, new_side)
        _write(directory, "before", name, before)
        _write(directory, "after", name, after)
        written += 1
    if not written:
        raise ValueError("no file of the diff was selected")


def _skeleton(directory: Path, data: dict[str, Any]) -> None:
    """case.yaml with the changed line ranges listed as hints for the expected findings."""
    files = build_files(directory)
    languages = Counter(f["language"] for f in files)
    data["language"] = languages.most_common(1)[0][0] if languages else "unknown"
    hints = []
    for file in files:
        for hunk in parse_patch(file["patch"]).hunks:
            added = [line.new_line for line in hunk.lines if line.kind == "add" and line.new_line]
            if added:
                hints.append(f"#   {file['filename']}: lines {min(added)}-{max(added)} added")
            else:
                context = [line.new_line for line in hunk.lines if line.new_line]
                where = f"{min(context)}-{max(context)}" if context else "?"
                hints.append(f"#   {file['filename']}: only removals, around lines {where}")
    text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)
    text += (
        "# Changed code (hints for expected_findings / must_not_flag):\n" + "\n".join(hints) + "\n"
    )
    (directory / "case.yaml").write_text(text, encoding="utf-8", newline="\n")


def fetch_commit_case(
    repo: str, sha: str, case_id: str, *, reverse: bool, paths: list[str] | None
) -> Path:
    directory = CASES_DIR / case_id
    if directory.exists():
        raise FileExistsError(f"{directory} already exists")
    with _client() as client:
        diff = _get(client, f"{WEB}/{repo}/commit/{sha}.diff").text
        _materialize(client, directory, repo, sha, diff, reverse=reverse, paths=paths)
        license_id = _license(client, repo)
    _skeleton(
        directory,
        {
            "id": case_id,
            "split": "dev",
            "source": "cve" if reverse else "oss",
            "language": "",
            "title": "TODO: neutral pull request title",
            "description": "TODO",
            "origin": {
                "repo": repo,
                "url": f"{WEB}/{repo}/commit/{sha}",
                "license": license_id,
                "commit": sha,
            },
            "expected_findings": [],
            "must_not_flag": [],
        },
    )
    return directory


def fetch_pr_case(repo: str, number: int, case_id: str, *, paths: list[str] | None) -> Path:
    directory = CASES_DIR / case_id
    if directory.exists():
        raise FileExistsError(f"{directory} already exists")
    with _client() as client:
        pr = _get(client, f"{API}/repos/{repo}/pulls/{number}").json()
        head = pr["head"]["sha"]
        diff = _get(client, f"{WEB}/{repo}/pull/{number}.diff").text
        _materialize(client, directory, repo, head, diff, reverse=False, paths=paths)
        license_id = _license(client, repo)
    _skeleton(
        directory,
        {
            "id": case_id,
            "split": "dev",
            "source": "oss",
            "language": "",
            "title": pr["title"],
            "description": "Merged pull request reviewed by the maintainers.",
            "origin": {
                "repo": repo,
                "url": pr["html_url"],
                "license": license_id,
                "commit": head,
            },
            "must_not_flag": [],
        },
    )
    return directory
