"""
LangGraph graph construction — builds the review pipeline with parallel fan-out/fan-in.
"""

import asyncio
import json
import uuid
import structlog
from typing import Dict, Any

from langgraph.graph import StateGraph, END

from app.config import settings
from app.graph.state import PRState
from app.graph.supervisor import supervisor_node
from app.graph.agents.security import security_agent_node
from app.graph.agents.quality import quality_agent_node
from app.graph.agents.performance import performance_agent_node
from app.graph.synthesis import synthesis_node
from app.db import crud

log = structlog.get_logger()


async def hitl_node(state: PRState) -> Dict[str, Any]:
    """Human-in-the-loop breakpoint. Waits for user approval via API."""
    review_id = state.get("review_id", "")

    await crud.create_event(
        review_id=review_id,
        event_type="hitl_waiting",
        message="Waiting for human review and approval...",
    )

    await crud.update_review(review_id, status="hitl_pending")

    # In a real implementation, this would pause the graph using LangGraph's
    # interrupt_before mechanism. For now, we mark it and the API will resume.
    return {
        "status": "hitl_pending",
        "hitl_approved": None,
    }


def should_go_to_hitl(state: PRState) -> str:
    """Conditional edge: route to HITL or END based on config."""
    if settings.HITL_ENABLED and not state.get("hitl_approved"):
        return "hitl"
    return END


def build_graph() -> StateGraph:
    """Build and compile the review LangGraph pipeline."""
    graph = StateGraph(PRState)

    # Add nodes
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("security", security_agent_node)
    graph.add_node("quality", quality_agent_node)
    graph.add_node("performance", performance_agent_node)
    graph.add_node("synthesis", synthesis_node)
    graph.add_node("hitl", hitl_node)

    # Set entry point
    graph.set_entry_point("supervisor")

    # Supervisor → 3 agents in parallel (fan-out)
    graph.add_edge("supervisor", "security")
    graph.add_edge("supervisor", "quality")
    graph.add_edge("supervisor", "performance")

    # Fan-in: all three agents must complete before synthesis
    graph.add_edge("security", "synthesis")
    graph.add_edge("quality", "synthesis")
    graph.add_edge("performance", "synthesis")

    # Conditional: HITL enabled or go to END
    graph.add_conditional_edges(
        "synthesis",
        should_go_to_hitl,
        {"hitl": "hitl", END: END},
    )

    graph.add_edge("hitl", END)

    return graph.compile()


# Build the graph once at module load
review_graph = build_graph()


async def run_review(review_id: str, repo: str, pr_number: int, commit_id: str, files: list, pr_metadata: dict = None) -> dict:
    """Run the review graph for a PR."""
    log.info("review_graph_started", review_id=review_id, repo=repo, pr_number=pr_number)

    await crud.update_review(review_id, status="running")
    await crud.create_event(
        review_id=review_id,
        event_type="review_start",
        message=f"Starting review of PR #{pr_number} in {repo}",
        data={"repo": repo, "pr_number": pr_number},
    )

    initial_state = PRState(
        repo=repo,
        pr_number=pr_number,
        commit_id=commit_id,
        files=files,
        pr_metadata=pr_metadata or {},
        security_files=[],
        quality_files=[],
        performance_files=[],
        security_findings=[],
        quality_findings=[],
        performance_findings=[],
        all_findings=[],
        review_summary="",
        verdict="",
        events=[],
        hitl_approved=None,
        hitl_modified_findings=None,
        review_id=review_id,
        status="running",
        error=None,
    )

    try:
        result = await review_graph.ainvoke(initial_state)

        await crud.create_event(
            review_id=review_id,
            event_type="review_complete",
            message=f"Review complete. Verdict: {result.get('verdict', 'unknown')}",
            data={"verdict": result.get("verdict", ""), "findings_count": len(result.get("all_findings", []))},
        )

        log.info("review_graph_completed", review_id=review_id, verdict=result.get("verdict"))
        return result

    except Exception as e:
        log.error("review_graph_failed", review_id=review_id, error=str(e))
        await crud.update_review(review_id, status="failed", error=str(e))
        await crud.create_event(
            review_id=review_id,
            event_type="review_error",
            message=f"Review failed: {str(e)}",
        )
        return {"error": str(e), "status": "failed"}
