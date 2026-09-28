"""Supervisor: review scope, deterministic security coverage and LLM triage."""

from unittest.mock import AsyncMock

import pytest

from app.config import settings
from app.graph import supervisor
from app.graph.schemas import SupervisorAssignment


def _file(name: str, patch: str = "@@ -1 +1 @@\n+x = 1") -> dict:
    return {"filename": name, "language": "python", "patch": patch, "additions": 1, "deletions": 0}


def _state(files: list[dict]) -> dict:
    return {"review_id": "r1", "repo": "o/r", "pr_number": 1, "files": files}


@pytest.fixture(autouse=True)
def no_events(monkeypatch):
    monkeypatch.setattr(supervisor.crud, "create_event", AsyncMock())


@pytest.fixture
def triage(monkeypatch):
    fake = AsyncMock()
    monkeypatch.setattr(supervisor, "invoke_structured", fake)
    return fake


async def test_small_pr_goes_to_every_agent_without_an_llm_call(triage):
    result = await supervisor.supervisor_node(_state([_file("a.py"), _file("b.py")]))

    assert result["security_files"] == ["a.py", "b.py"]
    assert result["quality_files"] == ["a.py", "b.py"]
    assert result["performance_files"] == ["a.py", "b.py"]
    triage.assert_not_awaited()


async def test_large_pr_is_triaged_and_security_still_gets_every_file(triage):
    names = [f"f{i}.py" for i in range(5)]
    triage.return_value = SupervisorAssignment(
        quality_files=["f0.py", "f1.py", "ghost.py"], performance_files=["f2.py"]
    )

    result = await supervisor.supervisor_node(_state([_file(n) for n in names]))

    assert result["security_files"] == names  # not left to the model
    assert result["quality_files"] == ["f0.py", "f1.py"]  # invented path dropped
    assert result["performance_files"] == ["f2.py"]


async def test_triage_failure_falls_back_to_every_agent(triage):
    names = [f"f{i}.py" for i in range(5)]
    triage.side_effect = RuntimeError("model down")

    result = await supervisor.supervisor_node(_state([_file(n) for n in names]))

    assert result["quality_files"] == names
    assert result["errors"][0]["agent"] == "supervisor"


async def test_generated_and_binary_files_are_skipped(triage):
    files = [_file("app.py"), _file("package-lock.json"), _file("logo.png", patch="")]

    result = await supervisor.supervisor_node(_state(files))

    assert result["security_files"] == ["app.py"]
    skipped = {s["filename"]: s["reason"] for s in result["skipped_files"]}
    assert set(skipped) == {"package-lock.json", "logo.png"}
    assert "no textual diff" in skipped["logo.png"]


async def test_size_limits_cut_the_review(triage, monkeypatch):
    monkeypatch.setattr(settings, "MAX_REVIEW_FILES", 2)
    files = [_file(f"f{i}.py") for i in range(3)]

    result = await supervisor.supervisor_node(_state(files))

    assert result["security_files"] == ["f0.py", "f1.py"]
    assert result["skipped_files"][0]["reason"].startswith("review limit of 2 files")


async def test_extra_exclude_patterns_from_settings(triage, monkeypatch):
    monkeypatch.setattr(settings, "REVIEW_EXCLUDE_PATTERNS", "docs/*")

    result = await supervisor.supervisor_node(_state([_file("docs/a.md"), _file("app.py")]))

    assert result["security_files"] == ["app.py"]


async def test_pr_without_reviewable_files(triage):
    result = await supervisor.supervisor_node(_state([_file("yarn.lock")]))

    assert result["security_files"] == []
    triage.assert_not_awaited()
