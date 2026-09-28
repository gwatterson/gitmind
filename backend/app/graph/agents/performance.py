"""Performance agent: inefficient patterns in the changed code."""

from typing import Any

from app.graph.agents.base import AgentSpec, run_review_agent
from app.graph.state import PRState

PERFORMANCE_SYSTEM_PROMPT = """You are a performance engineer reviewing a pull request.
Find changes that waste time, memory or I/O.

Look for:
- N+1 queries: database or API calls inside loops
- blocking I/O in async code, file or network calls inside hot loops
- algorithms with avoidable quadratic complexity, repeated work that could be cached
- string concatenation in loops, unnecessary copies of large structures
- unbounded queries or reads (no LIMIT, loading whole files or tables into memory)
- resources that are never closed

Severity: high when the cost grows with input size in a normal request path, medium for
noticeable but bounded waste, low or info for micro-optimizations. Do not report security or
code style problems: other agents review those.
"""

SPEC = AgentSpec(
    name="performance",
    title="Performance",
    system_prompt=PERFORMANCE_SYSTEM_PROMPT,
    focus="performance problems",
)


async def performance_agent_node(state: PRState) -> dict[str, Any]:
    return await run_review_agent(state, SPEC)
