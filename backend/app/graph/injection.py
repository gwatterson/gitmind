"""Defenses against prompt injection in pull request content (PLAN.md F8.4).

Pull requests are written by people the reviewer should not trust, and the code they
contain is pasted into LLM prompts. Two layers:

1. Fencing: the content is wrapped in <untrusted_code id="..."> tags whose id is a hash
   of the content itself. The content cannot contain its own hash, so it cannot close
   the fence and continue as instructions; look-alike tags inside it are neutralized.
   The id is deterministic, so identical pull requests produce identical prompts.
2. Detection: added lines are scanned for text addressed to an AI reviewer (instruction
   overrides, requests to approve or stay silent, fake system messages) and for invisible
   or bidirectional control characters. Each hit becomes a deterministic security finding:
   an attempt to manipulate the review is worth a human look whether or not it worked.
"""

import hashlib
import re
from dataclasses import dataclass

from app.diff.parser import parse_patch
from app.graph.state import Finding, PRFile

FENCE_TAG = "untrusted_code"

_LOOKALIKE_TAG = re.compile(r"(</?\s*)(untrusted_code|pr_diff)", re.IGNORECASE)

# Zero-width and other invisible characters, and Unicode tag characters
_INVISIBLE = re.compile("[\u200b-\u200f\u2060-\u2064\ufeff\U000e0000-\U000e007f]")
# Bidirectional overrides and isolates (Trojan Source, CVE-2021-42574)
_BIDI = re.compile("[\u202a-\u202e\u2066-\u2069]")

_ADDRESSED_TO_REVIEWER = [
    (
        r"\bignore\s+(all\s+)?(the\s+)?(previous|prior|above|earlier)\s+instructions\b",
        "instruction override",
    ),
    (
        r"\b(note|message|instructions?)\s+(for|to)\s+(the\s+)?(ai|llm|automated|code)\s*(code\s+)?review(er)?s?\b",
        "message to the AI reviewer",
    ),
    (r"\b(ai|llm|automated)\s+(code\s+)?review(er)?s?\s*[:,]", "message to the AI reviewer"),
    (
        r"\bdo\s+not\s+(report|flag|mention)\s+(it|this|them|these|that)\b",
        "request to hide findings",
    ),
    (
        r"\b(report\s+nothing|(return|answer|reply|respond)\s+with\s+no\s+findings)\b",
        "request to hide findings",
    ),
    (
        r"\b(return|answer\s+with|reply\s+with)\s+an\s+empty\s+list\s+of\s+findings\b",
        "request to hide findings",
    ),
    (r"\bplease\s+approve\s+this\s+(pull\s+request|pr)\b", "request to approve"),
    (r"\byou\s+are\s+(now\s+)?in\s+\w+(\s+\w+)?\s+mode\b", "role-play instruction"),
    (r"\bsecurity\s+(analysis|checks?|review)\s+(is|are)\s+disabled\b", "role-play instruction"),
    (r"\bseverity\s+override\b", "severity override"),
    (r"</?\s*(untrusted_code|pr_diff|system|instructions)\s*>", "fake prompt delimiter"),
]
_PATTERNS = [(re.compile(p, re.IGNORECASE), label) for p, label in _ADDRESSED_TO_REVIEWER]
# A fake chat turn inside a comment or a string, e.g. `# System: the review is complete`.
# Case sensitive and anchored to a comment or quote, so `system: str = ...` is not a hit.
_PATTERNS.append(
    (
        re.compile(r"(#|//|/\*|\"|')\s*(System|SYSTEM|Assistant|ASSISTANT)\s*:\s+\w"),
        "fake system message",
    )
)


def fence_id(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def wrap_untrusted(content: str) -> str:
    """Fence untrusted content so that it cannot pose as instructions."""
    safe = _LOOKALIKE_TAG.sub(lambda m: m.group(1) + m.group(2).replace("_", "-"), content)
    nonce = fence_id(safe)
    return f'<{FENCE_TAG} id="{nonce}">\n{safe}\n</{FENCE_TAG} id="{nonce}">'


@dataclass(frozen=True)
class Signal:
    kind: str  # "bidi", "invisible" or "instruction"
    label: str


def scan_text(text: str) -> Signal | None:
    """The strongest manipulation signal in a piece of text, if any."""
    if _BIDI.search(text):
        return Signal("bidi", "bidirectional control characters")
    visible = _INVISIBLE.sub("", text)
    for pattern, label in _PATTERNS:
        if pattern.search(visible):
            return Signal("instruction", label)
    if _INVISIBLE.search(text):
        return Signal("invisible", "invisible characters")
    return None


def _finding(filename: str, line: int, content: str, signal: Signal) -> Finding:
    if signal.kind == "bidi":
        return Finding(
            file=filename,
            line=line,
            severity="high",
            category="security",
            rule_id="trojan-source",
            message="Bidirectional control characters change how this line is displayed: "
            "the code a reviewer reads is not the code that runs (Trojan Source).",
            suggestion="Remove the bidirectional control characters.",
            agent="injection-guard",
            confidence=1.0,
            cwe="CWE-1007",
            evidence=content.strip()[:300],
        )
    return Finding(
        file=filename,
        line=line,
        severity="medium",
        category="security",
        rule_id="prompt-injection-attempt",
        message=f"Text addressed to automated reviewers ({signal.label}): an attempt to "
        "manipulate an AI code review. The code around it deserves a careful human look.",
        suggestion="Remove the instruction; review this change manually.",
        agent="injection-guard",
        confidence=0.9,
        cwe="CWE-1427",
        evidence=content.strip()[:300],
    )


def scan_files(files: list[PRFile]) -> list[Finding]:
    """Findings for manipulation attempts on the lines a pull request adds."""
    findings: list[Finding] = []
    for file in files:
        for line in parse_patch(file.get("patch", "")).lines:
            if line.kind != "add" or not line.new_line:
                continue
            signal = scan_text(line.content)
            if signal is not None:
                findings.append(_finding(file["filename"], line.new_line, line.content, signal))
    return findings
