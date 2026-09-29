"""Versioned prompt files: loading, validation and the prompts directory override."""

import pytest

from app.config import settings
from app.graph.agents.base import agent_system_prompt
from app.graph.prompts import (
    PROMPT_NAMES,
    PromptError,
    get_prompt,
    parse_prompt,
    prompt_versions,
)


def test_every_pipeline_prompt_loads_with_a_version():
    for name in PROMPT_NAMES:
        prompt = get_prompt(name)
        assert prompt.version
        assert prompt.text
        assert "---" not in prompt.text.splitlines()[0]
        assert len(prompt.sha) == 8


def test_prompt_versions_lists_every_prompt():
    refs = prompt_versions().split(",")
    assert [ref.split("@")[0] for ref in refs] == list(PROMPT_NAMES)


def test_agent_prompt_ends_with_the_shared_rules():
    prompt = agent_system_prompt("security")
    assert prompt.startswith(get_prompt("security").text)
    assert prompt.endswith(get_prompt("agent_rules").text)
    assert "<pr_diff>" in prompt


@pytest.mark.parametrize(
    ("content", "error"),
    [
        ("no front matter", "no front matter"),
        ("---\nversion: 1\n", "unterminated"),
        ("---\ndescription: x\n---\ntext", "no version"),
        ("---\nversion: 1\n---\n   \n", "empty"),
    ],
)
def test_malformed_prompts_are_rejected(content, error):
    with pytest.raises(PromptError, match=error):
        parse_prompt("broken", content)


def test_windows_line_endings_are_normalized():
    prompt = parse_prompt("p", "---\r\nversion: 3\r\n---\r\nline one\r\nline two\r\n")
    assert prompt.version == "3"
    assert prompt.text == "line one\nline two"
    assert prompt.ref == "p@3"


def test_prompts_dir_selects_an_alternative_prompt_set(tmp_path, monkeypatch):
    for name in PROMPT_NAMES:
        (tmp_path / f"{name}.md").write_text(
            f"---\nversion: 99\n---\nExperimental {name} prompt\n", encoding="utf-8"
        )
    monkeypatch.setattr(settings, "PROMPTS_DIR", str(tmp_path))
    assert get_prompt("security").text == "Experimental security prompt"
    assert prompt_versions().startswith("security@99,")


def test_missing_prompt_file_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROMPTS_DIR", str(tmp_path))
    with pytest.raises(PromptError, match="not found"):
        get_prompt("security")
