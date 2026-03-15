"""
MCP Server — custom Model Context Protocol server exposing GitHub and analysis tools.
Runs as a separate process using stdio transport.
"""

import asyncio
import json
import os
import subprocess
import tempfile
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Initialize MCP server
server = Server("gitmind-mcp")


def _get_github_client():
    """Get authenticated GitHub client."""
    from github import Github, GithubIntegration
    from app.config import settings

    import logging
    log = logging.getLogger(__name__)
    app_id = settings.GITHUB_APP_ID
    private_key_path = settings.GITHUB_PRIVATE_KEY_PATH

    log.info(f"CLIENT_INIT app_id={app_id!r} priv_key={private_key_path!r}")

    if not app_id or not private_key_path:
        # Fallback to token-based auth for development
        token = settings.GITHUB_TOKEN
        log.info(f"CLIENT_INIT using token fallback, token len: {len(token)}")
        if token:
            log.info("CLIENT_INIT returning Github(token)")
            return Github(token)
        log.info("CLIENT_INIT token was empty, returning None")
        return None

    try:
        with open(private_key_path, "r") as f:
            private_key = f.read()
        integration = GithubIntegration(int(app_id), private_key)
        # For simplicity, get the first installation
        installations = integration.get_installations()
        if installations:
            install_id = installations[0].id
            access_token = integration.get_access_token(install_id).token
            log.info("CLIENT_INIT returning Github App")
            return Github(access_token)
    except Exception as e:
        log.info(f"CLIENT_INIT exception in GithubIntegration: {e}")
        pass

    log.info("CLIENT_INIT returning None at end")
    return None


# ──────────────────────────────────────────────
# Tool Definitions
# ──────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_pr_diff",
            description="Fetches the full PR diff with per-file metadata.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "Repository in owner/name format"},
                    "pr_number": {"type": "integer", "description": "Pull request number"},
                },
                "required": ["repo", "pr_number"],
            },
        ),
        Tool(
            name="list_pr_files",
            description="Lists modified files with metadata.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string"},
                    "pr_number": {"type": "integer"},
                },
                "required": ["repo", "pr_number"],
            },
        ),
        Tool(
            name="post_review_comment",
            description="Posts an inline comment on a specific diff line.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string"},
                    "pr_number": {"type": "integer"},
                    "body": {"type": "string"},
                    "commit_id": {"type": "string"},
                    "path": {"type": "string"},
                    "line": {"type": "integer"},
                    "side": {"type": "string", "enum": ["LEFT", "RIGHT"]},
                },
                "required": ["repo", "pr_number", "body", "commit_id", "path", "line"],
            },
        ),
        Tool(
            name="post_review_summary",
            description="Posts the overall review with a verdict.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string"},
                    "pr_number": {"type": "integer"},
                    "body": {"type": "string"},
                    "event": {"type": "string", "enum": ["COMMENT", "APPROVE", "REQUEST_CHANGES"]},
                },
                "required": ["repo", "pr_number", "body", "event"],
            },
        ),
        Tool(
            name="get_pr_metadata",
            description="Fetches PR metadata (title, author, branches, labels).",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string"},
                    "pr_number": {"type": "integer"},
                },
                "required": ["repo", "pr_number"],
            },
        ),
        Tool(
            name="semgrep_scan",
            description="Runs semgrep static analysis on a code snippet.",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "language": {"type": "string"},
                    "ruleset": {"type": "string", "enum": ["auto", "security", "owasp"]},
                },
                "required": ["code", "language"],
            },
        ),
        Tool(
            name="calculate_complexity",
            description="Calculates cyclomatic and cognitive complexity metrics.",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "language": {"type": "string"},
                },
                "required": ["code", "language"],
            },
        ),
        Tool(
            name="parse_ast",
            description="Parses code into an AST for structural analysis.",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "language": {"type": "string"},
                },
                "required": ["code", "language"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Route tool calls to implementation functions."""
    handlers = {
        "get_pr_diff": handle_get_pr_diff,
        "list_pr_files": handle_list_pr_files,
        "post_review_comment": handle_post_review_comment,
        "post_review_summary": handle_post_review_summary,
        "get_pr_metadata": handle_get_pr_metadata,
        "semgrep_scan": handle_semgrep_scan,
        "calculate_complexity": handle_calculate_complexity,
        "parse_ast": handle_parse_ast,
    }

    handler = handlers.get(name)
    if not handler:
        return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

    try:
        result = await handler(arguments)
        return [TextContent(type="text", text=json.dumps(result, default=str))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


# ──────────────────────────────────────────────
# GitHub Tool Implementations
# ──────────────────────────────────────────────

async def handle_get_pr_diff(args: dict) -> dict:
    """Fetch PR diff with per-file metadata."""
    gh = _get_github_client()
    if not gh:
        return {"error": "GitHub client not configured"}

    repo = gh.get_repo(args["repo"])
    pr = repo.get_pull(args["pr_number"])
    files_data = []

    for f in pr.get_files():
        files_data.append({
            "filename": f.filename,
            "patch": f.patch or "",
            "additions": f.additions,
            "deletions": f.deletions,
            "status": f.status,
        })

    return {"files": files_data}


async def handle_list_pr_files(args: dict) -> dict:
    """List modified files with metadata."""
    gh = _get_github_client()
    if not gh:
        return {"error": "GitHub client not configured"}

    repo = gh.get_repo(args["repo"])
    pr = repo.get_pull(args["pr_number"])
    files_data = []

    for f in pr.get_files():
        # Detect language from extension
        ext = os.path.splitext(f.filename)[1].lower()
        lang_map = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".jsx": "javascript", ".tsx": "typescript", ".go": "go",
            ".java": "java", ".rb": "ruby", ".rs": "rust",
        }
        files_data.append({
            "filename": f.filename,
            "language": lang_map.get(ext, "unknown"),
            "size_bytes": f.raw_data.get("size", 0) if hasattr(f, "raw_data") else 0,
        })

    return {"files": files_data}


async def handle_post_review_comment(args: dict) -> dict:
    """Post an inline comment on a specific line."""
    gh = _get_github_client()
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
    gh = _get_github_client()
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
    gh = _get_github_client()
    if not gh:
        return {"error": "GitHub client not configured"}

    repo = gh.get_repo(args["repo"])
    pr = repo.get_pull(args["pr_number"])

    return {
        "title": pr.title,
        "author": pr.user.login,
        "base_branch": pr.base.ref,
        "head_branch": pr.head.ref,
        "created_at": str(pr.created_at),
        "labels": [l.name for l in pr.labels],
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
        config = f"p/{ruleset}" if ruleset != "auto" else "auto"
        result = subprocess.run(
            ["semgrep", "--config", config, "--json", tmp_path],
            capture_output=True, text=True, timeout=30,
        )

        if result.returncode == 0:
            output = json.loads(result.stdout)
            findings = []
            for r in output.get("results", []):
                findings.append({
                    "rule_id": r.get("check_id", ""),
                    "message": r.get("extra", {}).get("message", ""),
                    "severity": r.get("extra", {}).get("severity", "WARNING").lower(),
                    "line": r.get("start", {}).get("line", 0),
                })
            return {"findings": findings}
        else:
            return {"findings": [], "note": "semgrep returned non-zero exit code"}

    except FileNotFoundError:
        return {"findings": [], "note": "semgrep not installed — skipped"}
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
            from radon.complexity import cc_visit
            from radon.metrics import mi_visit

            blocks = cc_visit(code)
            functions = []
            for block in blocks:
                functions.append({
                    "name": block.name,
                    "complexity": block.complexity,
                    "line": block.lineno,
                    "rank": block.letter,
                })

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
        patterns = [r'\bif\b', r'\belse\b', r'\bfor\b', r'\bwhile\b',
                     r'\bcase\b', r'\bcatch\b', r'\b\&\&\b', r'\b\|\|\b']
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
            issues = []

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    classes.append({"name": node.name, "line": node.lineno})
                elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                    functions.append({
                        "name": node.name,
                        "line": node.lineno,
                        "args": len(node.args.args),
                        "has_docstring": (
                            isinstance(node.body[0], ast.Expr) and
                            isinstance(node.body[0].value, (ast.Str, ast.Constant))
                        ) if node.body else False,
                    })
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
            return {"error": f"Syntax error: {e}", "classes": [], "functions": [], "imports": [], "issues": []}
    else:
        # Basic regex-based parsing for JS/TS
        import re
        functions = [{"name": m.group(1), "line": 0}
                     for m in re.finditer(r'(?:function|const|let|var)\s+(\w+)', code)]
        classes = [{"name": m.group(1), "line": 0}
                   for m in re.finditer(r'class\s+(\w+)', code)]
        imports = [m.group(0) for m in re.finditer(r'import\s+.*', code)]

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

async def main():
    """Run the MCP server via stdio."""
    from dotenv import load_dotenv
    load_dotenv()

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
