"""Language detection and the rules that keep files out of a review."""

import fnmatch
import os

LANGUAGES = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".java": "java",
    ".kt": "kotlin",
    ".rb": "ruby",
    ".rs": "rust",
    ".php": "php",
    ".cs": "csharp",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".swift": "swift",
    ".scala": "scala",
    ".sql": "sql",
    ".sh": "shell",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".tf": "terraform",
    ".html": "html",
    ".vue": "vue",
}

_SPECIAL_NAMES = {"dockerfile": "dockerfile", "makefile": "makefile"}

# Files that are generated, vendored or not reviewable as code
DEFAULT_EXCLUDE_PATTERNS = (
    "*package-lock.json",
    "*yarn.lock",
    "*pnpm-lock.yaml",
    "*uv.lock",
    "*poetry.lock",
    "*Pipfile.lock",
    "*Cargo.lock",
    "*go.sum",
    "*composer.lock",
    "*Gemfile.lock",
    "*.min.js",
    "*.min.css",
    "*.map",
    "*.snap",
    "*_pb2.py",
    "*.pb.go",
    "*.svg",
    "node_modules/*",
    "*/node_modules/*",
    "vendor/*",
    "*/vendor/*",
    "dist/*",
    "*/dist/*",
    "build/*",
    "*/build/*",
    ".next/*",
    "*/.next/*",
)


def detect_language(filename: str) -> str:
    base = os.path.basename(filename).lower()
    if base in _SPECIAL_NAMES:
        return _SPECIAL_NAMES[base]
    return LANGUAGES.get(os.path.splitext(base)[1], "unknown")


def exclusion_reason(filename: str, patch: str, extra_patterns: list[str]) -> str | None:
    """Why a file is left out of the review, or None if it should be reviewed."""
    if not patch.strip():
        # GitHub omits the patch for binary files, pure renames and very large diffs
        return "no textual diff (binary, rename only, or too large for GitHub)"
    for pattern in (*DEFAULT_EXCLUDE_PATTERNS, *extra_patterns):
        if fnmatch.fnmatch(filename, pattern):
            return f"excluded by pattern {pattern}"
    return None
