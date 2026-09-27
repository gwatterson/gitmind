"""LangGraph shared state definitions for PR review pipeline."""

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class PRFile(TypedDict):
    """Represents a file modified in a pull request."""

    filename: str
    language: str
    patch: str
    additions: int
    deletions: int


class Finding(TypedDict):
    """A single review finding from any agent."""

    file: str
    line: int
    severity: str  # "critical" | "high" | "medium" | "low" | "info"
    category: str  # "security" | "quality" | "performance"
    rule_id: str
    message: str
    suggestion: str
    agent: str


class PRState(TypedDict):
    """Complete state for the PR review LangGraph pipeline."""

    # Input
    repo: str
    pr_number: int
    commit_id: str

    # Extracted data
    files: list[PRFile]
    pr_metadata: dict

    # Agent assignment (decided by the Supervisor)
    security_files: list[str]
    quality_files: list[str]
    performance_files: list[str]

    # Agent outputs
    security_findings: list[Finding]
    quality_findings: list[Finding]
    performance_findings: list[Finding]

    # Final output
    all_findings: list[Finding]
    review_summary: str
    verdict: str  # "approve" | "comment" | "request_changes"

    # Streaming events (for SSE)
    events: Annotated[list[str], add_messages]

    # Human-in-the-loop
    hitl_approved: bool | None
    hitl_modified_findings: list[Finding] | None

    # Tracking
    review_id: str
    status: str
    error: str | None
