"""Performance agent: inefficient patterns in the changed code."""

from typing import Any

from app.graph.agents.base import AgentSpec, run_review_agent
from app.graph.state import PRState

SPEC = AgentSpec(
    name="performance",
    title="Performance",
    focus="performance problems",
)


async def performance_agent_node(state: PRState) -> dict[str, Any]:
    return await run_review_agent(state, SPEC)
