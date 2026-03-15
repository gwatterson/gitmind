"""LangGraph shared state definitions for PR review pipeline."""

from typing import TypedDict, List, Optional, Annotated
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
    severity: str           # "critical" | "high" | "medium" | "low" | "info"
    category: str           # "security" | "quality" | "performance"
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
    files: List[PRFile]
    pr_metadata: dict

    # Agent assignment (decided by the Supervisor)
    security_files: List[str]
    quality_files: List[str]
    performance_files: List[str]

    # Agent outputs
    security_findings: List[Finding]
    quality_findings: List[Finding]
    performance_findings: List[Finding]

    # Final output
    all_findings: List[Finding]
    review_summary: str
    verdict: str            # "approve" | "comment" | "request_changes"

    # Streaming events (for SSE)
    events: Annotated[List[str], add_messages]

    # Human-in-the-loop
    hitl_approved: Optional[bool]
    hitl_modified_findings: Optional[List[Finding]]

    # Tracking
    review_id: str
    status: str
    error: Optional[str]
