"""
MCP server exposing GitHub and static analysis tools (Model Context Protocol, SDK v2).

Run it as a separate process over stdio: python -m app.mcp_server.server
The handle_* functions are also imported directly by the review pipeline.
"""

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer

from app.github.client import get_github_client

server = MCPServer(
    "gitmind-mcp",
    instructions="GitHub pull request and static analysis tools used by the GitMind code reviewer.",
)


# ──────────────────────────────────────────────
# Tool definitions (input schemas are generated from the type hints)
# ──────────────────────────────────────────────


@server.tool(description="Fetches the full PR diff with per-file metadata.")
async def get_pr_diff(repo: str, pr_number: int) -> dict[str, Any]:
    """repo is in owner/name format."""
    return await handle_get_pr_diff({"repo": repo, "pr_number": pr_number})


@server.tool(description="Lists modified files with metadata.")
async def list_pr_files(repo: str, pr_number: int) -> dict[str, Any]:
    return await handle_list_pr_files({"repo": repo, "pr_number": pr_number})


@server.tool(description="Posts an inline comment on a specific diff line.")
async def post_review_comment(
    repo: str,
    pr_number: int,
    body: str,
    commit_id: str,
    path: str,
    line: int,
    side: Literal["LEFT", "RIGHT"] = "RIGHT",
) -> dict[str, Any]:
    return await handle_post_review_comment(
        {
            "repo": repo,
            "pr_number": pr_number,
            "body": body,
            "commit_id": commit_id,
            "path": path,
            "line": line,
            "side": side,
        }
    )


@server.tool(description="Posts the overall review with a verdict.")
async def post_review_summary(
    repo: str,
    pr_number: int,
    body: str,
    event: Literal["COMMENT", "APPROVE", "REQUEST_CHANGES"] = "COMMENT",
) -> dict[str, Any]:
    return await handle_post_review_summary(
        {"repo": repo, "pr_number": pr_number, "body": body, "event": event}
    )


@server.tool(description="Fetches PR metadata (title, author, branches, labels).")
async def get_pr_metadata(repo: str, pr_number: int) -> dict[str, Any]:
    return await handle_get_pr_metadata({"repo": repo, "pr_number": pr_number})


@server.tool(description="Runs semgrep static analysis on a code snippet.")
async def semgrep_scan(
    code: str,
    language: str = "python",
    ruleset: Literal["auto", "security", "owasp"] = "auto",
) -> dict[str, Any]:
    return await handle_semgrep_scan({"code": code, "language": language, "ruleset": ruleset})


@server.tool(description="Calculates cyclomatic and cognitive complexity metrics.")
async def calculate_complexity(code: str, language: str = "python") -> dict[str, Any]:
    return await handle_calculate_complexity({"code": code, "language": language})


@server.tool(description="Parses code into an AST for structural analysis.")
async def parse_ast(code: str, language: str = "python") -> dict[str, Any]:
    return await handle_parse_ast({"code": code, "language": language})


# ──────────────────────────────────────────────
# GitHub Tool Implementations
# ──────────────────────────────────────────────


async def handle_get_pr_diff(args: dict) -> dict:
    """Fetch PR diff with per-file metadata."""
    gh = get_github_client()
    if not gh:
        return {"error": "GitHub client not configured"}

    repo = gh.get_repo(args["repo"])
    pr = repo.get_pull(args["pr_number"])
    files_data = []

    for f in pr.get_files():
        files_data.append(
            {
                "filename": f.filename,
                "patch": f.patch or "",
                "additions": f.additions,
                "deletions": f.deletions,
                "status": f.status,
            }
        )

    return {"files": files_data}


async def handle_list_pr_files(args: dict) -> dict:
    """List modified files with metadata."""
    gh = get_github_client()
    if not gh:
        return {"error": "GitHub client not configured"}

    repo = gh.get_repo(args["repo"])
    pr = repo.get_pull(args["pr_number"])
    files_data = []

    for f in pr.get_files():
        # Detect language from extension
        ext = os.path.splitext(f.filename)[1].lower()
        lang_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".jsx": "javascript",
            ".tsx": "typescript",
            ".go": "go",
            ".java": "java",
            ".rb": "ruby",
            ".rs": "rust",
        }
        files_data.append(
            {
                "filename": f.filename,
                "language": lang_map.get(ext, "unknown"),
                "size_bytes": f.raw_data.get("size", 0) if hasattr(f, "raw_data") else 0,
            }
        )

    return {"files": files_data}


async def handle_post_review_comment(args: dict) -> dict:
    """Post an inline comment on a specific line."""
    gh = get_github_client()
    if not gh:
        return {"error": "GitHub client not configured"}

    repo = gh.get_repo(args["repo"])
    pr = repo.get_pull(args["pr_number"])

    comment = pr.create_review_comment(
        body=args["body"],
        commit=repo.get_commit(args["commit_id"]),
        path=args["path"],
        line=args["line"],
        side=args.get("side", "RIGHT"),
    )

    return {"comment_id": comment.id, "url": comment.html_url}


async def handle_post_review_summary(args: dict) -> dict:
    """Post overall review with verdict."""
    gh = get_github_client()
    if not gh:
        return {"error": "GitHub client not configured"}

    repo = gh.get_repo(args["repo"])
    pr = repo.get_pull(args["pr_number"])

    review = pr.create_review(
        body=args["body"],
        event=args.get("event", "COMMENT"),
    )

    return {"review_id": review.id}


async def handle_get_pr_metadata(args: dict) -> dict:
    """Fetch PR metadata."""
    gh = get_github_client()
    if not gh:
        return {"error": "GitHub client not configured"}

    repo = gh.get_repo(args["repo"])
    pr = repo.get_pull(args["pr_number"])

    return {
        "title": pr.title,
        "author": pr.user.login,
        "base_branch": pr.base.ref,
        "head_branch": pr.head.ref,
        "head_sha": pr.head.sha,
        "created_at": str(pr.created_at),
        "labels": [label.name for label in pr.labels],
    }


# ──────────────────────────────────────────────
# Analysis Tool Implementations
# ──────────────────────────────────────────────


async def handle_semgrep_scan(args: dict) -> dict:
    """Run semgrep on a code snippet."""
    code = args["code"]
    language = args.get("language", "python")
    ruleset = args.get("ruleset", "auto")

    ext_map = {"python": ".py", "javascript": ".js", "typescript": ".ts"}
    ext = ext_map.get(language, ".py")

    with tempfile.NamedTemporaryFile(mode="w", suffix=ext, delete=False) as f:
        f.write(code)
        tmp_path = f.name

    try:
        semgrep_bin = shutil.which("semgrep")
        if semgrep_bin is None:
            return {"findings": [], "note": "semgrep not installed, skipped"}

        config = f"p/{ruleset}" if ruleset != "auto" else "auto"
        # Fixed argument list, no shell: arguments cannot inject commands.
        # Run in a worker thread so the event loop is not blocked.
        result = await asyncio.to_thread(
            subprocess.run,
            [semgrep_bin, "--config", config, "--json", tmp_path],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            output = json.loads(result.stdout)
            findings = []
            for r in output.get("results", []):
                findings.append(
                    {
                        "rule_id": r.get("check_id", ""),
                        "message": r.get("extra", {}).get("message", ""),
                        "severity": r.get("extra", {}).get("severity", "WARNING").lower(),
                        "line": r.get("start", {}).get("line", 0),
                    }
                )
            return {"findings": findings}
        else:
            return {"findings": [], "note": "semgrep returned non-zero exit code"}

    except FileNotFoundError:
        return {"findings": [], "note": "semgrep not installed, skipped"}
    except subprocess.TimeoutExpired:
        return {"findings": [], "note": "semgrep timed out"}
    except Exception as e:
        return {"findings": [], "error": str(e)}
    finally:
        os.unlink(tmp_path)


async def handle_calculate_complexity(args: dict) -> dict:
    """Calculate cyclomatic complexity using radon."""
    code = args["code"]
    language = args.get("language", "python")

    if language == "python":
        try:
            from radon.complexity import cc_rank, cc_visit
            from radon.metrics import mi_visit

            blocks = cc_visit(code)
            functions = []
            for block in blocks:
                functions.append(
                    {
                        "name": block.name,
                        "complexity": block.complexity,
                        "line": block.lineno,
                        "rank": cc_rank(block.complexity),
                    }
                )

            avg_complexity = sum(b.complexity for b in blocks) / len(blocks) if blocks else 0
            maintainability = mi_visit(code, True)

            return {
                "cyclomatic_complexity": round(avg_complexity, 2),
                "maintainability_index": round(maintainability, 2),
                "functions": functions,
            }
        except Exception as e:
            return {"error": str(e), "functions": []}
    else:
        # Regex-based fallback for JS/TS
        import re

        patterns = [
            r"\bif\b",
            r"\belse\b",
            r"\bfor\b",
            r"\bwhile\b",
            r"\bcase\b",
            r"\bcatch\b",
            r"\b\&\&\b",
            r"\b\|\|\b",
        ]
        total = 1  # Base complexity
        for p in patterns:
            total += len(re.findall(p, code))
        return {
            "cyclomatic_complexity": total,
            "cognitive_complexity": total,
            "functions": [],
            "note": "Regex-based estimate for non-Python code",
        }


async def handle_parse_ast(args: dict) -> dict:
    """Parse code for structural analysis."""
    code = args["code"]
    language = args.get("language", "python")

    if language == "python":
        import ast

        try:
            tree = ast.parse(code)
            classes = []
            functions = []
            imports = []
            issues: list[dict] = []

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    classes.append({"name": node.name, "line": node.lineno})
                elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                    functions.append(
                        {
                            "name": node.name,
                            "line": node.lineno,
                            "args": len(node.args.args),
                            "has_docstring": (
                                isinstance(node.body[0], ast.Expr)
                                and isinstance(node.body[0].value, (ast.Str, ast.Constant))
                            )
                            if node.body
                            else False,
                        }
                    )
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    imports.append(f"{node.module}" if node.module else "")

            return {
                "classes": classes,
                "functions": functions,
                "imports": imports,
                "issues": issues,
            }
        except SyntaxError as e:
            return {
                "error": f"Syntax error: {e}",
                "classes": [],
                "functions": [],
                "imports": [],
                "issues": [],
            }
    else:
        # Basic regex-based parsing for JS/TS
        import re

        functions = [
            {"name": m.group(1), "line": 0}
            for m in re.finditer(r"(?:function|const|let|var)\s+(\w+)", code)
        ]
        classes = [{"name": m.group(1), "line": 0} for m in re.finditer(r"class\s+(\w+)", code)]
        imports = [m.group(0) for m in re.finditer(r"import\s+.*", code)]

        return {
            "classes": classes,
            "functions": functions,
            "imports": imports,
            "issues": [],
            "note": "Regex-based parsing for non-Python code",
        }


# ──────────────────────────────────────────────
# Server Entry Point
# ──────────────────────────────────────────────


def main() -> None:
    """Run the MCP server over stdio: python -m app.mcp_server.server"""
    from dotenv import load_dotenv

    load_dotenv()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
