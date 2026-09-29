"""
LangGraph graph construction: builds the review pipeline with parallel fan-out/fan-in.
"""

from typing import Any

import structlog
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.config import settings
from app.db import crud
from app.graph.agents.performance import performance_agent_node
from app.graph.agents.quality import quality_agent_node
from app.graph.agents.security import security_agent_node
from app.graph.prompts import prompt_versions
from app.graph.state import PRState
from app.graph.supervisor import supervisor_node
from app.graph.synthesis import findings_only_synthesis_node, synthesis_node
from app.graph.verifier import verify_node
from app.llm import factory
from app.rate_limiter import DailyQuotaExhaustedError
from app.services import publisher

log = structlog.get_logger()


async def hitl_node(state: PRState) -> dict[str, Any]:
    """Human-in-the-loop breakpoint. Waits for user approval via API."""
    review_id = state.get("review_id", "")

    await crud.create_event(
        review_id=review_id,
        event_type="hitl_waiting",
        message="Waiting for human review and approval...",
    )

    await crud.update_review(review_id, status="hitl_pending")

    # The graph ends here; POST /api/reviews/{id}/approve publishes the review.
    # Native LangGraph interrupt() with a checkpointer: PLAN.md F8.7.
    return {
        "status": "hitl_pending",
        "hitl_approved": None,
    }


async def publish_node(state: PRState) -> dict[str, Any]:
    """Post the review to GitHub automatically (used when HITL is disabled)."""
    review_id = state.get("review_id", "")
    result = await publisher.publish_review(review_id, human_approved=False)

    if result.posted:
        message = f"Review posted to GitHub ({result.comments_posted} inline comment(s))."
    else:
        message = result.warning or "Review not posted to GitHub."
    if result.posted and result.warning:
        message += " " + result.warning

    await crud.create_event(
        review_id=review_id,
        event_type="publish_done" if result.posted else "publish_skipped",
        message=message,
        data={
            "posted": result.posted,
            "comments_posted": result.comments_posted,
            "comments_failed": result.comments_failed,
        },
    )
    return {}


def route_after_synthesis(state: PRState) -> str:
    """Stop failed reviews, wait for a human when HITL is on, otherwise publish."""
    if state.get("status") == "failed":
        return END
    if settings.HITL_ENABLED:
        return "hitl"
    return "publish"


def build_graph(*, deliver: bool = True) -> CompiledStateGraph:
    """Build and compile the review LangGraph pipeline.

    With deliver=False the graph stops after synthesis, without the summary LLM call,
    human approval or publishing: this is the graph measured by the evaluation.
    """
    graph = StateGraph(PRState)

    graph.add_node("supervisor", supervisor_node)
    graph.add_node("security", security_agent_node)
    graph.add_node("quality", quality_agent_node)
    graph.add_node("performance", performance_agent_node)
    graph.add_node("verify", verify_node)
    graph.add_node("synthesis", synthesis_node if deliver else findings_only_synthesis_node)

    graph.set_entry_point("supervisor")

    # Supervisor → 3 agents in parallel (fan-out)
    graph.add_edge("supervisor", "security")
    graph.add_edge("supervisor", "quality")
    graph.add_edge("supervisor", "performance")

    # Fan-in: all three agents must complete before the verifier checks their findings
    graph.add_edge("security", "verify")
    graph.add_edge("quality", "verify")
    graph.add_edge("performance", "verify")
    graph.add_edge("verify", "synthesis")

    if not deliver:
        graph.add_edge("synthesis", END)
        return graph.compile()

    graph.add_node("hitl", hitl_node)
    graph.add_node("publish", publish_node)
    graph.add_conditional_edges(
        "synthesis",
        route_after_synthesis,
        {"hitl": "hitl", "publish": "publish", END: END},
    )
    graph.add_edge("hitl", END)
    graph.add_edge("publish", END)

    return graph.compile()


# Build the graph once at module load
review_graph = build_graph()


def initial_state(
    *,
    review_id: str,
    repo: str,
    pr_number: int,
    commit_id: str,
    files: list,
    pr_metadata: dict | None = None,
) -> PRState:
    """The state a review starts from: the pull request files and empty results."""
    return PRState(
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
        hitl_approved=None,
        hitl_modified_findings=None,
        review_id=review_id,
        status="running",
        errors=[],
    )


async def run_review(
    review_id: str,
    repo: str,
    pr_number: int,
    commit_id: str,
    files: list,
    pr_metadata: dict | None = None,
) -> dict:
    """Run the review graph for a PR."""
    log.info("review_graph_started", review_id=review_id, repo=repo, pr_number=pr_number)

    await crud.update_review(
        review_id,
        status="running",
        llm_provider=factory.provider_name(),
        llm_model=factory.model_name(),
        prompt_versions=prompt_versions(),
    )
    await crud.create_event(
        review_id=review_id,
        event_type="review_start",
        message=f"Starting review of PR #{pr_number} in {repo} "
        f"with {factory.model_name()} ({factory.provider_name()})",
        data={"repo": repo, "pr_number": pr_number, "llm_model": factory.model_name()},
    )

    state = initial_state(
        review_id=review_id,
        repo=repo,
        pr_number=pr_number,
        commit_id=commit_id,
        files=files,
        pr_metadata=pr_metadata,
    )

    try:
        result = await review_graph.ainvoke(state)
    except DailyQuotaExhaustedError as e:
        log.warning("review_quota_exhausted", review_id=review_id)
        await crud.update_review(
            review_id, status="quota_exhausted", error=str(e), completed_at=crud.utc_now()
        )
        await crud.create_event(
            review_id=review_id,
            event_type="review_error",
            message=f"LLM daily quota exhausted: trigger the review again later. {e}",
        )
        return {"status": "quota_exhausted"}
    except Exception as e:
        log.error(
            "review_graph_failed", review_id=review_id, error_type=type(e).__name__, error=str(e)
        )
        await crud.update_review(
            review_id,
            status="failed",
            error=f"Unexpected error ({type(e).__name__}). See the server logs.",
            completed_at=crud.utc_now(),
        )
        await crud.create_event(
            review_id=review_id,
            event_type="review_error",
            message=f"Review failed with an unexpected error ({type(e).__name__}).",
        )
        return {"status": "failed"}

    if result.get("status") == "failed":
        await crud.create_event(
            review_id=review_id,
            event_type="review_error",
            message="Review failed: every agent reported an error.",
        )
        return result

    await crud.create_event(
        review_id=review_id,
        event_type="review_complete",
        message=f"Review complete. Verdict: {result.get('verdict', 'unknown')}",
        data={
            "verdict": result.get("verdict", ""),
            "findings_count": len(result.get("all_findings", [])),
        },
    )
    log.info("review_graph_completed", review_id=review_id, verdict=result.get("verdict"))
    return result
