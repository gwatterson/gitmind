"""Tests for MCP tools: verify output structure and behavior."""

import pytest

from app.mcp_server.server import (
    handle_calculate_complexity,
    handle_parse_ast,
    handle_semgrep_scan,
)


@pytest.mark.asyncio
async def test_calculate_complexity_python():
    """Verify complexity calculation for Python code."""
    code = """
def simple_function(x):
    return x + 1

def complex_function(x, y, z):
    if x > 0:
        if y > 0:
            if z > 0:
                return x + y + z
            else:
                return x + y
        else:
            return x
    elif x == 0:
        return 0
    else:
        for i in range(y):
            if i % 2 == 0:
                z += i
        return z
"""
    result = await handle_calculate_complexity({"code": code, "language": "python"})

    assert "cyclomatic_complexity" in result
    assert "functions" in result
    assert len(result["functions"]) == 2
    # complex_function should have higher complexity
    complexities = {f["name"]: f["complexity"] for f in result["functions"]}
    assert complexities["complex_function"] > complexities["simple_function"]


@pytest.mark.asyncio
async def test_parse_ast_python():
    """Verify AST parsing output structure for Python."""
    code = '''
import os
from typing import List

class MyClass:
    def method_one(self):
        pass

    def method_two(self, x: int) -> str:
        """Documented method."""
        return str(x)

def standalone_func():
    pass
'''
    result = await handle_parse_ast({"code": code, "language": "python"})

    assert "classes" in result
    assert "functions" in result
    assert "imports" in result

    # Should find 1 class
    assert len(result["classes"]) >= 1
    assert result["classes"][0]["name"] == "MyClass"

    # Should find functions
    func_names = [f["name"] for f in result["functions"]]
    assert "standalone_func" in func_names
    assert "method_one" in func_names


@pytest.mark.asyncio
async def test_semgrep_scan_graceful_degradation():
    """Semgrep should gracefully degrade when not installed."""
    code = 'print("hello")'
    result = await handle_semgrep_scan({"code": code, "language": "python"})

    # Should return a valid structure regardless of semgrep availability
    assert "findings" in result
    assert isinstance(result["findings"], list)


@pytest.mark.asyncio
async def test_calculate_complexity_javascript():
    """Verify regex-based complexity for JavaScript."""
    code = """
function processData(items) {
    if (items.length === 0) return;
    for (let i = 0; i < items.length; i++) {
        if (items[i].active && items[i].valid) {
            while (items[i].pending) {
                items[i].process();
            }
        }
    }
}
"""
    result = await handle_calculate_complexity({"code": code, "language": "javascript"})

    assert "cyclomatic_complexity" in result
    assert result["cyclomatic_complexity"] > 1  # Should detect control flow


@pytest.mark.asyncio
async def test_parse_ast_javascript():
    """Verify regex-based parsing for JavaScript."""
    code = """
import { useState } from 'react';
class MyComponent {}
function handleClick() {}
const processData = () => {};
"""
    result = await handle_parse_ast({"code": code, "language": "javascript"})

    assert "classes" in result
    assert "functions" in result
    assert "imports" in result
    assert len(result["classes"]) >= 1


async def test_complexity_rank_is_the_radon_grade():
    """rank is the A-F complexity grade, not the block type letter."""
    code = "def f(x):\n    return x\n"
    result = await handle_calculate_complexity({"code": code, "language": "python"})
    assert result["functions"][0]["rank"] == "A"


async def test_mcp_server_registers_all_tools_with_schemas():
    from app.mcp_server.server import server

    tools = {tool.name: tool for tool in await server.list_tools()}

    assert set(tools) == {
        "get_pr_diff",
        "list_pr_files",
        "post_review_comment",
        "post_review_summary",
        "get_pr_metadata",
        "semgrep_scan",
        "calculate_complexity",
        "parse_ast",
    }
    schema = tools["post_review_summary"].input_schema
    assert set(schema["required"]) == {"repo", "pr_number", "body"}
    assert schema["properties"]["event"]["enum"] == ["COMMENT", "APPROVE", "REQUEST_CHANGES"]


async def test_mcp_tool_call_returns_structured_content():
    from app.mcp_server.server import server

    result = await server.call_tool("parse_ast", {"code": "class A:\n    pass\n"})

    assert not result.is_error
    assert result.structured_content["classes"][0]["name"] == "A"
