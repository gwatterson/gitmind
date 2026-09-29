"""Quality agent: correctness risks and maintainability of the changed code."""

from typing import Any

from app.graph.agents.base import AgentSpec, run_review_agent
from app.graph.state import PRState

SPEC = AgentSpec(
    name="quality",
    title="Quality",
    focus="code quality and correctness",
)


async def quality_agent_node(state: PRState) -> dict[str, Any]:
    return await run_review_agent(state, SPEC)
