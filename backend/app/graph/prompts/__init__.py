"""Versioned prompts of the review pipeline.

Each prompt is a markdown file in this directory with a small front matter:

    ---
    version: 2
    description: What the prompt is for
    ---
    Prompt text...

Bump `version` whenever the text changes: the versions are stored with every
review and every evaluation run (see eval/README.md), so results can always be
traced back to the prompts that produced them. PROMPTS_DIR can point to another
directory with the same file names, to evaluate an experimental prompt set
without touching this one.
"""

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.config import settings

DEFAULT_PROMPTS_DIR = Path(__file__).parent

PROMPT_NAMES = ("security", "quality", "performance", "agent_rules", "supervisor", "synthesis")


class PromptError(ValueError):
    """A prompt file is missing or malformed."""


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    description: str
    text: str

    @property
    def ref(self) -> str:
        """Short reference such as security@2."""
        return f"{self.name}@{self.version}"

    @property
    def sha(self) -> str:
        """Content fingerprint: tells two edits apart even if the version was not bumped."""
        return hashlib.sha256(self.text.encode()).hexdigest()[:8]


def parse_prompt(name: str, content: str) -> Prompt:
    """Split the front matter from the prompt text."""
    content = content.replace("\r\n", "\n")
    if not content.startswith("---\n"):
        raise PromptError(f"Prompt '{name}' has no front matter")
    header, separator, body = content[4:].partition("\n---\n")
    if not separator:
        raise PromptError(f"Prompt '{name}' has an unterminated front matter")
    meta: dict[str, str] = {}
    for line in header.splitlines():
        key, colon, value = line.partition(":")
        if colon:
            meta[key.strip()] = value.strip()
    if not meta.get("version"):
        raise PromptError(f"Prompt '{name}' has no version")
    text = body.strip()
    if not text:
        raise PromptError(f"Prompt '{name}' is empty")
    return Prompt(
        name=name, version=meta["version"], description=meta.get("description", ""), text=text
    )


@lru_cache(maxsize=64)
def _load(name: str, directory: str) -> Prompt:
    path = Path(directory) / f"{name}.md"
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise PromptError(f"Prompt file not found: {path}") from None
    return parse_prompt(name, content)


def prompts_dir() -> Path:
    return Path(settings.PROMPTS_DIR) if settings.PROMPTS_DIR else DEFAULT_PROMPTS_DIR


def get_prompt(name: str) -> Prompt:
    """Load a prompt from the active prompts directory (cached)."""
    return _load(name, str(prompts_dir()))


def prompt_versions() -> str:
    """All prompt references of the pipeline, e.g. 'security@1,quality@2,...'."""
    return ",".join(get_prompt(name).ref for name in PROMPT_NAMES)
