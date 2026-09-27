"""LangGraph shared state definitions for PR review pipeline."""

import operator
from typing import Annotated, TypedDict


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


class AgentError(TypedDict):
    """A failure of one node of the pipeline. The review can still complete."""

    agent: str
    message: str


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

    # Human-in-the-loop
    hitl_approved: bool | None
    hitl_modified_findings: list[Finding] | None

    # Tracking
    review_id: str
    status: str
    # Parallel agents can fail in the same step: the reducer concatenates their
    # errors instead of raising InvalidUpdateError on concurrent writes.
    errors: Annotated[list[AgentError], operator.add]
