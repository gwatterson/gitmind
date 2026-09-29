"""LangGraph shared state definitions for PR review pipeline."""

import operator
from typing import Annotated, NotRequired, TypedDict


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
    confidence: NotRequired[float]  # 0-1, as estimated by the agent
    cwe: NotRequired[str | None]
    evidence: NotRequired[str]  # code fragment quoted from the diff
    verifier_confidence: NotRequired[float]  # set by the verifier node
    verifier_note: NotRequired[str]
    verifier_real: NotRequired[bool]


class SkippedFile(TypedDict):
    """A changed file left out of the review, with the reason shown in the summary."""

    filename: str
    reason: str


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

    # Files left out of the review (generated, binary, over the size limits)
    skipped_files: NotRequired[list[SkippedFile]]

    # Agent assignment (decided by the Supervisor)
    security_files: list[str]
    quality_files: list[str]
    performance_files: list[str]

    # Agent outputs
    security_findings: list[Finding]
    quality_findings: list[Finding]
    performance_findings: list[Finding]

    # Findings the verifier did not confirm: stored for analysis, never published
    suppressed_findings: NotRequired[list[Finding]]

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
