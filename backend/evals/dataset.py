"""Evaluation dataset: one directory per case.

    eval/dataset/cases/<case-id>/
        case.yaml          metadata and expected findings
        before/<path>      file content before the pull request (absent for new files)
        after/<path>       file content after the pull request (absent for deleted files)

The diff given to the pipeline is generated from before/ and after/, in the same
format as the `patch` field of the GitHub API. Keeping the full files (instead of
the diff alone) lets static analyzers such as semgrep run on the same cases.
"""

import difflib
import hashlib
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, PrivateAttr, field_validator, model_validator

from app.diff.files import detect_language
from app.diff.parser import parse_patch
from app.graph.state import PRFile

EVAL_DIR = Path(__file__).resolve().parents[2] / "eval"
CASES_DIR = EVAL_DIR / "dataset" / "cases"

Category = Literal["security", "quality", "performance"]
Source = Literal["synthetic", "cve", "oss"]  # oss: merged open source pull requests
Split = Literal["dev", "test"]
Severity = Literal["critical", "high", "medium", "low", "info"]

SEVERITY_RANK: dict[str, int] = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}

DIFF_CONTEXT_LINES = 3


class LineRange(BaseModel):
    """Inclusive range of lines in the new version of a file.

    The range is given either as line numbers or, easier to write and to review, as
    an `anchor`: a code fragment found on exactly one line of the file (the first
    line of the range), optionally followed by `span` more lines.
    """

    file: str
    lines: tuple[int, int] | None = None
    anchor: str | None = None
    span: int = 0

    @field_validator("lines", mode="before")
    @classmethod
    def _single_line(cls, value: object) -> object:
        if isinstance(value, int):
            return (value, value)
        return value

    @model_validator(mode="after")
    def _located(self) -> "LineRange":
        if self.lines is None and not self.anchor:
            raise ValueError(f"{self.file}: give either `lines` or `anchor`")
        if self.lines is not None:
            start, end = self.lines
            if start < 1 or end < start:
                raise ValueError(f"{self.file}: invalid line range {self.lines}")
        return self

    def resolve(self, content: list[str]) -> None:
        """Turn the anchor into line numbers (content: lines of the new file)."""
        if not self.anchor:
            return
        needle = " ".join(self.anchor.split())
        found = [i for i, line in enumerate(content, start=1) if needle in " ".join(line.split())]
        if len(found) != 1:
            raise ValueError(
                f"{self.file}: anchor {self.anchor!r} found on {len(found)} lines, expected 1"
            )
        self.lines = (found[0], found[0] + self.span)

    def distance(self, line: int) -> int:
        """0 inside the range, otherwise how many lines away."""
        if self.lines is None:
            raise ValueError(f"{self.file}: unresolved anchor {self.anchor!r}")
        start, end = self.lines
        if line < start:
            return start - line
        return max(line - end, 0)


class ExpectedFinding(LineRange):
    category: Category
    cwe: list[str] = Field(default_factory=list)  # accepted CWE ids, security only
    severity_min: Severity = "low"
    description: str
    # Other places where the same problem appears (e.g. the same unsafe call repeated):
    # a finding on any of them detects the problem, further ones are duplicates.
    also: list[LineRange] = Field(default_factory=list)

    @property
    def locations(self) -> list[LineRange]:
        return [self, *self.also]

    @field_validator("cwe", mode="before")
    @classmethod
    def _as_list(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return value


class SafeLines(LineRange):
    """Lines that look suspicious but are correct: a finding there is a false positive."""

    reason: str


class Origin(BaseModel):
    """Where a real-world case comes from."""

    repo: str
    url: str
    license: str
    commit: str | None = None
    parent: str | None = None
    advisory: str | None = None
    cve: str | None = None


class Case(BaseModel):
    id: str
    split: Split
    source: Source
    language: str
    title: str
    description: str
    smoke: bool = False  # part of the small subset used by the CI regression gate
    origin: Origin | None = None
    expected_findings: list[ExpectedFinding] = Field(default_factory=list)
    must_not_flag: list[SafeLines] = Field(default_factory=list)

    # Filled by the loader (a case rebuilt from a results file has neither)
    _files: list[PRFile] = PrivateAttr(default_factory=list)
    _directory: Path | None = PrivateAttr(default=None)

    @model_validator(mode="after")
    def _consistent(self) -> "Case":
        if self.source == "oss" and self.expected_findings:
            raise ValueError("open source pull requests are used as clean cases")
        if self.source == "cve" and not self.expected_findings:
            raise ValueError("a CVE case needs its expected finding")
        if self.source != "synthetic" and self.origin is None:
            raise ValueError("real-world cases need an origin")
        return self

    @property
    def files(self) -> list[PRFile]:
        return self._files

    @property
    def directory(self) -> Path | None:
        return self._directory

    @property
    def is_clean(self) -> bool:
        """No expected finding: every finding is a false positive."""
        return not self.expected_findings

    @property
    def expects_block(self) -> bool:
        """A human reviewer would request changes on this pull request."""
        return any(
            SEVERITY_RANK[e.severity_min] >= SEVERITY_RANK["high"] for e in self.expected_findings
        )


def _read(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n").splitlines()


def make_patch(before: list[str], after: list[str]) -> str:
    """Unified diff without the ---/+++ header, like the GitHub API `patch` field."""
    lines = list(difflib.unified_diff(before, after, n=DIFF_CONTEXT_LINES, lineterm=""))
    return "\n".join(lines[2:])


def _relative_files(root: Path) -> set[str]:
    if not root.is_dir():
        return set()
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


def build_files(directory: Path) -> list[PRFile]:
    """Diff before/ against after/ and return the changed files as the pipeline sees them."""
    before_dir, after_dir = directory / "before", directory / "after"
    files: list[PRFile] = []
    for name in sorted(_relative_files(before_dir) | _relative_files(after_dir)):
        before = _read(before_dir / name) if (before_dir / name).is_file() else []
        after = _read(after_dir / name) if (after_dir / name).is_file() else []
        if before == after:
            continue
        patch = make_patch(before, after)
        parsed = parse_patch(patch)
        files.append(
            PRFile(
                filename=name,
                language=detect_language(name),
                patch=patch,
                additions=sum(1 for line in parsed.lines if line.kind == "add"),
                deletions=sum(1 for line in parsed.lines if line.kind == "del"),
            )
        )
    return files


def load_case(directory: Path) -> Case:
    data = yaml.safe_load((directory / "case.yaml").read_text(encoding="utf-8"))
    case = Case.model_validate(data)
    if case.id != directory.name:
        raise ValueError(f"case id '{case.id}' does not match its directory '{directory.name}'")
    case._directory = directory
    case._files = build_files(directory)
    alternatives = [loc for e in case.expected_findings for loc in e.also]
    for item in [*case.expected_findings, *alternatives, *case.must_not_flag]:
        path = directory / "after" / item.file
        if item.anchor and path.is_file():
            item.resolve(_read(path))
    if not case.files:
        raise ValueError(f"case '{case.id}' has no changed files")
    return case


def load_cases(
    split: str = "all",
    *,
    sources: set[str] | None = None,
    ids: set[str] | None = None,
    smoke: bool = False,
    cases_dir: Path = CASES_DIR,
) -> list[Case]:
    """Load the cases of a split ("dev", "test" or "all"), optionally filtered."""
    cases = []
    for directory in sorted(p for p in cases_dir.iterdir() if (p / "case.yaml").is_file()):
        case = load_case(directory)
        if split != "all" and case.split != split:
            continue
        if sources and case.source not in sources:
            continue
        if ids and case.id not in ids:
            continue
        if smoke and not case.smoke:
            continue
        cases.append(case)
    return cases


def dataset_fingerprint(cases: list[Case]) -> str:
    """Hash of the cases' definitions and diffs: two runs on the same fingerprint are comparable."""
    digest = hashlib.sha256()
    for case in sorted(cases, key=lambda c: c.id):
        digest.update(case.model_dump_json().encode())
        for file in case.files:
            digest.update(file["filename"].encode())
            digest.update(file["patch"].encode())
    return digest.hexdigest()[:12]


def validate_case(case: Case) -> list[str]:
    """Problems that would make a case's expectations unmeasurable."""
    problems = []
    parsed = {f["filename"]: parse_patch(f["patch"]) for f in case.files}
    ranges: list[tuple[str, LineRange]] = [
        ("expected", loc) for e in case.expected_findings for loc in e.locations
    ]
    ranges += [("must_not_flag", s) for s in case.must_not_flag]
    for kind, item in ranges:
        patch = parsed.get(item.file)
        if patch is None:
            problems.append(f"{kind} {item.file}:{item.lines}: file not in the diff")
            continue
        if item.lines is None:
            problems.append(f"{kind} {item.file}: anchor {item.anchor!r} not resolved")
            continue
        start, end = item.lines
        if not any(start <= line <= end for line in patch.commentable_lines):
            problems.append(f"{kind} {item.file}:{item.lines}: no line of the range is in the diff")
    for expected in case.expected_findings:
        if expected.category != "security" and expected.cwe:
            problems.append(
                f"expected {expected.file}:{expected.lines}: CWE on a non-security finding"
            )
    return problems
