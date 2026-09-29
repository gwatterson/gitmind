"""Structured output schemas shared by the LLM nodes."""

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

Severity = Literal["critical", "high", "medium", "low", "info"]

_SEVERITY_ALIASES = {"error": "high", "warning": "medium", "moderate": "medium", "minor": "low"}


class ReviewFinding(BaseModel):
    """One problem reported by a review agent."""

    file: str = Field(description="File path exactly as written in the '### File:' header")
    line: int = Field(
        description=(
            "The line number printed at the start of the diff line with the problem. "
            "For a problem in removed code (a '-' line), use the nearest numbered line."
        )
    )
    severity: Severity
    rule_id: str = Field(description="Short kebab-case identifier, e.g. sql-injection")
    message: str = Field(description="What is wrong and why it matters, at most two sentences")
    suggestion: str = Field(
        default="", description="How to fix it, optionally with a short code example"
    )
    evidence: str = Field(
        default="", description="The exact code fragment from the diff that shows the problem"
    )
    # Required: with an optional field small models leave the default on almost every finding
    confidence: float = Field(
        description="Probability that this is a real problem: 0.9 certain, 0.6 plausible, 0.3 speculative",
    )
    cwe: str | None = Field(
        default=None, description="CWE identifier such as CWE-89 (security only)"
    )

    @field_validator("severity", mode="before")
    @classmethod
    def _normalize_severity(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip().lower()
            return _SEVERITY_ALIASES.get(value, value)
        return value

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp_confidence(cls, value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.5
        if number > 1:  # a percentage such as 85
            number = number / 100
        return min(max(number, 0.0), 1.0)

    @field_validator("cwe", mode="before")
    @classmethod
    def _normalize_cwe(cls, value: Any) -> str | None:
        if value is None:
            return None
        match = re.search(r"(\d+)", str(value))
        return f"CWE-{match.group(1)}" if match else None


class AgentReview(BaseModel):
    findings: list[ReviewFinding] = Field(default_factory=list)


class VerifierVerdict(BaseModel):
    id: int = Field(description="The id of the finding being judged")
    real: bool = Field(description="True if the code in the diff supports the finding")
    confidence: float = Field(description="Probability that the finding is real, 0 to 1")
    reason: str = Field(default="", description="One sentence")

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp_confidence(cls, value: Any) -> float:
        return ReviewFinding._clamp_confidence(value)


class VerifierReview(BaseModel):
    verdicts: list[VerifierVerdict] = Field(default_factory=list)


class SupervisorAssignment(BaseModel):
    """Which files need quality and performance review. Security reviews every file."""

    quality_files: list[str] = Field(default_factory=list)
    performance_files: list[str] = Field(default_factory=list)
    reasoning: str = Field(default="", description="One or two sentences")
