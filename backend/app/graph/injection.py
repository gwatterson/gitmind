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
   The text is normalized before matching, so that the same wording is found when it is
   spelled with look-alike letters, encoded in base64 or split over consecutive comments.
"""

import base64
import binascii
import hashlib
import re
import unicodedata
from collections.abc import Iterator
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

# Cyrillic and Greek letters that look like Latin ones (Unicode confusables), folded to
# Latin before matching. NFKC already folds fullwidth and other compatibility forms.
_LOOKALIKES = str.maketrans(
    # Cyrillic lowercase, then uppercase
    "\u0430\u0435\u043e\u0440\u0441\u0443\u0445\u0456\u0458\u0455\u0501\u04cf"
    "\u0410\u0412\u0415\u041a\u041c\u041d\u041e\u0420\u0421\u0422\u0425\u0405\u0406\u0408\u04ae"
    # Greek lowercase, then uppercase
    "\u03bf\u03b1\u03b9\u03ba\u03bd\u03c1\u03c4\u03c5\u03c7"
    "\u0391\u0392\u0395\u0396\u0397\u0399\u039a\u039c\u039d\u039f\u03a1\u03a4\u03a5\u03a7",
    "aeopcyxijsdlABEKMHOPCTXSIJYoaikvptuxABEZHIKMNOPTYX",
)
_BASE64_TOKEN = re.compile(r"[A-Za-z0-9+/]{24,}={0,2}")
# A comment line: its marker, removed when consecutive comment lines are joined
_COMMENT_LINE = re.compile(r"^\s*(#|//|/\*+|\*/|\*|--|<!--)\s?")


def _fold_lookalikes(text: str) -> str:
    return unicodedata.normalize("NFKC", text).translate(_LOOKALIKES)


def _base64_payloads(text: str) -> Iterator[str]:
    """Readable text hidden in base64 tokens; hashes and binary data decode to garbage."""
    for match in _BASE64_TOKEN.finditer(text):
        token = match.group()
        try:
            decoded = base64.b64decode(token + "=" * (-len(token) % 4), validate=True)
            payload = decoded.decode("utf-8")
        except (binascii.Error, ValueError):  # UnicodeDecodeError is a ValueError
            continue
        if payload.isprintable() and " " in payload:
            yield payload


def _variants(text: str) -> Iterator[tuple[str, str]]:
    """The text as written, then its normalized forms, each with a note for the finding."""
    yield text, ""
    folded = _fold_lookalikes(text)
    if folded != text:
        yield folded, ", spelled with look-alike letters"
    for payload in _base64_payloads(text):
        yield _fold_lookalikes(payload), ", base64 encoded"


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
    for variant, note in _variants(visible):
        for pattern, label in _PATTERNS:
            if pattern.search(variant):
                return Signal("instruction", label + note)
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


def _comment_blocks(lines: list[tuple[int, str]]) -> Iterator[list[tuple[int, str]]]:
    """Runs of two or more consecutive added comment lines, as (line number, content)."""
    block: list[tuple[int, str]] = []
    for number, content in lines:
        is_comment = bool(_COMMENT_LINE.match(content))
        if is_comment and (not block or number == block[-1][0] + 1):
            block.append((number, content))
            continue
        if len(block) > 1:
            yield block
        block = [(number, content)] if is_comment else []
    if len(block) > 1:
        yield block


def scan_files(files: list[PRFile]) -> list[Finding]:
    """Findings for manipulation attempts on the lines a pull request adds."""
    findings: list[Finding] = []
    for file in files:
        added = [
            (line.new_line, line.content)
            for line in parse_patch(file.get("patch", "")).lines
            if line.kind == "add" and line.new_line is not None
        ]
        flagged: set[int] = set()
        for number, content in added:
            signal = scan_text(content)
            if signal is not None:
                findings.append(_finding(file["filename"], number, content, signal))
                flagged.add(number)
        # An instruction split over several comment lines, so that no line reads as one
        for block in _comment_blocks(added):
            if any(number in flagged for number, _ in block):
                continue
            joined = " ".join(_COMMENT_LINE.sub("", content).strip() for _, content in block)
            signal = scan_text(joined)
            if signal is not None and signal.kind == "instruction":
                signal = Signal(signal.kind, signal.label + ", split over comment lines")
                findings.append(_finding(file["filename"], block[0][0], joined, signal))
    return findings
