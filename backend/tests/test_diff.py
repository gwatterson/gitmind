"""Diff parsing, numbered rendering, line resolution and file filters."""

import pytest

from app.diff.files import detect_language, exclusion_reason
from app.diff.parser import find_evidence_line, parse_patch, render_numbered, resolve_line

PATCH = """@@ -10,5 +10,6 @@ def handler(request):
     user = request.user
-    query = "SELECT * FROM t WHERE id=" + request.id
+    query = "SELECT * FROM t WHERE id=%s"
+    params = (request.id,)
     cursor.execute(query)
     return cursor.fetchall()
@@ -40,3 +41,3 @@ def other():
     a = 1
-    b = 2
+    b = 3
\\ No newline at end of file"""


def test_parse_assigns_old_and_new_line_numbers():
    parsed = parse_patch(PATCH)

    assert len(parsed.hunks) == 2
    first = parsed.hunks[0].lines
    assert (first[0].kind, first[0].old_line, first[0].new_line) == ("ctx", 10, 10)
    assert (first[1].kind, first[1].old_line, first[1].new_line) == ("del", 11, None)
    assert (first[2].kind, first[2].new_line) == ("add", 11)
    assert (first[3].kind, first[3].new_line) == ("add", 12)
    assert (first[4].kind, first[4].old_line, first[4].new_line) == ("ctx", 12, 13)
    second = parsed.hunks[1].lines
    assert [line.new_line for line in second] == [41, None, 42]


def test_no_newline_marker_is_ignored():
    parsed = parse_patch(PATCH)
    assert all("No newline" not in line.content for line in parsed.lines)


def test_commentable_lines_are_added_and_context_lines():
    parsed = parse_patch(PATCH)
    assert parsed.commentable_lines == {10, 11, 12, 13, 14, 41, 42}
    assert parsed.added_lines == {11, 12, 42}


def test_render_shows_new_line_numbers_and_markers():
    rendered = render_numbered(parse_patch(PATCH)).splitlines()

    assert rendered[0].startswith("@@ -10,5 +10,6 @@")
    assert rendered[1] == "   10       user = request.user"
    assert rendered[2].startswith("      - ")  # removed line: no number
    assert rendered[3] == '   11 +     query = "SELECT * FROM t WHERE id=%s"'


@pytest.mark.parametrize(
    ("reported", "expected"),
    [
        (11, (11, "exact")),  # added line
        (13, (13, "exact")),  # context line
        (15, (14, "nearest")),  # just after the hunk
        (16, (14, "nearest")),
        (18, (None, "none")),  # too far from the diff
        (40, (41, "nearest")),
        (0, (None, "none")),
        (None, (None, "none")),
    ],
)
def test_resolve_line(reported, expected):
    assert resolve_line(parse_patch(PATCH), reported) == expected


def test_resolve_prefers_added_lines_on_ties():
    patch = "@@ -1,2 +1,3 @@\n ctx\n+added\n ctx2"
    # line 2 is added; 1 and 3 are context; a reported line of 2 is exact
    assert resolve_line(parse_patch(patch), 2) == (2, "exact")
    patch_gap = "@@ -1,1 +1,1 @@\n ctx\n@@ -5,1 +5,1 @@\n+added"
    # 3 is equidistant from 1 (context) and 5 (added): the added line wins
    assert resolve_line(parse_patch(patch_gap), 3) == (5, "nearest")


def test_patch_without_hunks_has_no_commentable_lines():
    assert resolve_line(parse_patch(""), 5) == (None, "none")


@pytest.mark.parametrize(
    ("name", "language"),
    [
        ("app/main.py", "python"),
        ("web/App.TSX", "typescript"),
        ("infra/Dockerfile", "dockerfile"),
        ("README.md", "unknown"),
    ],
)
def test_detect_language(name, language):
    assert detect_language(name) == language


@pytest.mark.parametrize(
    "name",
    [
        "package-lock.json",
        "frontend/package-lock.json",
        "backend/uv.lock",
        "static/app.min.js",
        "vendor/lib/x.go",
        "api/proto/user_pb2.py",
        "web/dist/bundle.js",
    ],
)
def test_generated_and_vendored_files_are_excluded(name):
    assert exclusion_reason(name, "@@ -1 +1 @@\n+x", []) is not None


def test_files_without_patch_are_excluded():
    assert "no textual diff" in (exclusion_reason("image.png", "", []) or "")


def test_extra_patterns_and_regular_files():
    assert exclusion_reason("docs/guide.md", "+x", ["docs/*"]) == "excluded by pattern docs/*"
    assert exclusion_reason("app/main.py", "+x", ["docs/*"]) is None


EVIDENCE_PATCH = """@@ -1,4 +1,8 @@
 import sqlite3
+API_KEY = "sk-live-123"
+
+def login(user):
+    \"\"\"Log the user in.\"\"\"
+    query = f"SELECT * FROM users WHERE name='{user}'"
+    return db.execute(query)
 x = 1"""


def test_evidence_finds_the_real_line_when_the_reported_one_is_off():
    parsed = parse_patch(EVIDENCE_PATCH)
    evidence = "query = f\"SELECT * FROM users WHERE name='{user}'\""
    # The model pointed at the docstring (line 5): the quoted code is on line 6
    assert find_evidence_line(parsed, evidence, near=5) == 6


def test_evidence_matching_ignores_whitespace_and_uses_the_first_distinctive_line():
    parsed = parse_patch(EVIDENCE_PATCH)
    assert find_evidence_line(parsed, '\n  API_KEY   =  "sk-live-123"\n', near=20) == 2


def test_generic_or_missing_evidence_is_not_used():
    parsed = parse_patch(EVIDENCE_PATCH)
    assert find_evidence_line(parsed, "", near=3) is None
    assert find_evidence_line(parsed, "x", near=3) is None
    assert find_evidence_line(parsed, "not in the diff at all", near=3) is None


def test_closest_match_wins_when_the_code_repeats():
    patch = "@@ -1,1 +1,12 @@\n+run(query)\n" + "+pass\n" * 9 + "+run(query)\n+end"
    assert find_evidence_line(parse_patch(patch), "run(query)", near=10) == 11
    assert find_evidence_line(parse_patch(patch), "run(query)", near=2) == 1
