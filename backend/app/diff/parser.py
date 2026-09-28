"""Unified diff parsing for GitHub pull request patches.

GitHub returns one patch per file, made of hunks such as:

    @@ -10,4 +10,5 @@ def handler(request):
         query = build_query()
    -    run(query)
    +    safe = sanitize(query)
    +    run(safe)

Review comments can only be placed on lines that appear in the diff. On the
new version of the file (side RIGHT) those are added and context lines. This
module numbers every line, renders the patch with explicit line numbers for
the LLM, and maps the line the model reports back to a commentable line.
"""

import re
from dataclasses import dataclass, field
from typing import Literal

LineKind = Literal["add", "del", "ctx"]
LineResolution = Literal["exact", "nearest", "none"]

_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")

# Reported lines up to this distance from a commentable line are moved onto it
DEFAULT_TOLERANCE = 3


@dataclass(frozen=True)
class DiffLine:
    kind: LineKind
    content: str
    old_line: int | None
    new_line: int | None


@dataclass
class Hunk:
    header: str
    lines: list[DiffLine] = field(default_factory=list)


@dataclass
class ParsedPatch:
    hunks: list[Hunk] = field(default_factory=list)

    @property
    def lines(self) -> list[DiffLine]:
        return [line for hunk in self.hunks for line in hunk.lines]

    @property
    def commentable_lines(self) -> set[int]:
        """Lines of the new file that accept a review comment (side RIGHT)."""
        return {line.new_line for line in self.lines if line.new_line is not None}

    @property
    def added_lines(self) -> set[int]:
        return {line.new_line for line in self.lines if line.kind == "add" and line.new_line}


def parse_patch(patch: str) -> ParsedPatch:
    """Parse a GitHub file patch. Lines before the first hunk header are ignored."""
    parsed = ParsedPatch()
    current: Hunk | None = None
    old_no = new_no = 0

    for raw in patch.splitlines():
        match = _HUNK_HEADER.match(raw)
        if match:
            old_no = int(match.group(1))
            new_no = int(match.group(3))
            current = Hunk(header=raw)
            parsed.hunks.append(current)
            continue
        if current is None or raw.startswith("\\"):
            # Preamble, or "\ No newline at end of file"
            continue
        marker, content = raw[:1], raw[1:]
        if marker == "+":
            current.lines.append(DiffLine("add", content, None, new_no))
            new_no += 1
        elif marker == "-":
            current.lines.append(DiffLine("del", content, old_no, None))
            old_no += 1
        else:
            # Context line (a leading space, or an empty line in trimmed patches)
            current.lines.append(DiffLine("ctx", content, old_no, new_no))
            old_no += 1
            new_no += 1
    return parsed


def render_hunk(hunk: Hunk) -> str:
    """Render a hunk with the new-file line number in front of every line.

    Removed lines have no number in the new file, so their number column is empty.
    """
    rows = [hunk.header]
    for line in hunk.lines:
        number = f"{line.new_line:>5}" if line.new_line is not None else " " * 5
        marker = {"add": "+", "del": "-", "ctx": " "}[line.kind]
        rows.append(f"{number} {marker} {line.content}")
    return "\n".join(rows)


def render_numbered(parsed: ParsedPatch) -> str:
    return "\n".join(render_hunk(hunk) for hunk in parsed.hunks)


_WHITESPACE = re.compile(r"\s+")
# Evidence lines shorter than this (after normalization) are too generic to match
_MIN_EVIDENCE_CHARS = 6


def _normalize_code(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip()


def find_evidence_line(parsed: ParsedPatch, evidence: str, near: int | None = None) -> int | None:
    """Find the commentable line that contains the code quoted as evidence.

    Models are often off by a few lines when they report a line number, but they
    quote code faithfully. The first distinctive line of the evidence is searched
    in the new-file lines of the diff; with several matches, the one closest to
    the reported line wins.
    """
    candidates = [
        _normalize_code(line)
        for line in evidence.splitlines()
        if len(_normalize_code(line)) >= _MIN_EVIDENCE_CHARS
    ]
    if not candidates:
        return None
    needle = candidates[0]
    matches = [
        line.new_line
        for line in parsed.lines
        if line.new_line is not None
        and len(_normalize_code(line.content)) >= _MIN_EVIDENCE_CHARS
        and (needle in _normalize_code(line.content) or _normalize_code(line.content) in needle)
    ]
    if not matches:
        return None
    reference = near or matches[0]
    return min(matches, key=lambda m: (abs(m - reference), m))


def resolve_line(
    parsed: ParsedPatch, line: int | None, tolerance: int = DEFAULT_TOLERANCE
) -> tuple[int | None, LineResolution]:
    """Map a line reported by the model to a line GitHub accepts a comment on.

    Returns the line and how it was obtained: "exact", "nearest" (moved by at
    most `tolerance` lines, preferring added lines on ties), or "none" when the
    finding cannot be anchored to the diff and must be reported elsewhere.
    """
    commentable = parsed.commentable_lines
    if not line or line <= 0 or not commentable:
        return None, "none"
    if line in commentable:
        return line, "exact"

    added = parsed.added_lines
    candidates = [c for c in commentable if abs(c - line) <= tolerance]
    if not candidates:
        return None, "none"
    best = min(candidates, key=lambda c: (abs(c - line), c not in added, c))
    return best, "nearest"
