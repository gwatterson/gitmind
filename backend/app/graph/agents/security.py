"""Security agent: vulnerabilities in the changed code (OWASP Top 10 oriented)."""

from typing import Any

from app.graph.agents.base import AgentSpec, run_review_agent
from app.graph.state import PRState

SPEC = AgentSpec(
    name="security",
    title="Security",
    focus="security vulnerabilities",
)


async def security_agent_node(state: PRState) -> dict[str, Any]:
    return await run_review_agent(state, SPEC)
