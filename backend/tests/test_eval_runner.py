"""Evaluation runner end to end: real graph, scripted model, disk cache and CI gate."""

import argparse
import json
from pathlib import Path
from typing import Any

import pytest
from langchain_core.globals import set_llm_cache
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableLambda, RunnableParallel

from app.config import settings
from app.llm import factory
from evals import __main__ as cli
from evals import runner
from evals.dataset import Case, load_case
from evals.runner import RunConfig, run_evaluation
from tests.test_eval import write_case


class ScriptedChatModel(BaseChatModel):
    """Answers like a well-behaved model: one SQL injection finding for the security agent."""

    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(
        self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> ChatResult:
        self.calls += 1
        prompt = str(messages[-1].content)
        findings = []
        if "security vulnerabilities" in prompt and "### File: app/db.py" in prompt:
            findings.append(
                {
                    "file": "app/db.py",
                    "line": 6,
                    "severity": "high",
                    "rule_id": "sql-injection",
                    "message": "SQL built from user input",
                    "evidence": 'query = f"SELECT * FROM users',
                    "confidence": 0.9,
                    "cwe": "CWE-89",
                }
            )
        message = AIMessage(
            content=json.dumps({"findings": findings}),
            usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
        )
        return ChatResult(generations=[ChatGeneration(message=message)])

    def with_structured_output(
        self, schema: Any, *, include_raw: bool = False, **kwargs: Any
    ) -> Runnable:
        def parse(result: dict[str, Any]) -> dict[str, Any]:
            raw = result["raw"]
            return {
                "raw": raw,
                "parsed": schema.model_validate_json(raw.content),
                "parsing_error": None,
            }

        return RunnableParallel(raw=self) | RunnableLambda(parse)


@pytest.fixture
def eval_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ScriptedChatModel:
    """Scripted model, private cache directory, and settings restored after the test."""
    model = ScriptedChatModel()
    monkeypatch.setattr(factory, "get_chat_model", lambda *a, **k: model)
    monkeypatch.setattr(runner, "CACHE_DIR", tmp_path / "cache")
    for name in (
        "LLM_PROVIDER",
        "OLLAMA_MODEL",
        "HITL_ENABLED",
        "LLM_TIMEOUT_SECONDS",
        "PROMPTS_DIR",
    ):
        monkeypatch.setattr(settings, name, getattr(settings, name))
    yield model
    set_llm_cache(None)


@pytest.fixture
def case(tmp_path: Path) -> Case:
    return load_case(write_case(tmp_path / "cases"))


def config(cache_mode: str) -> RunConfig:
    return RunConfig(provider="ollama", model="scripted-model", cache_mode=cache_mode)  # type: ignore[arg-type]


async def test_run_records_answers_then_replays_them(eval_env, case, tmp_path):
    first = await run_evaluation(config("use"), [case], progress=lambda _: None)
    [result] = first["cases"]
    assert result["status"] == "ok"
    assert result["verdict"] == "request_changes"
    assert [(f["line"], f["category"], f["cwe"]) for f in result["findings"]] == [
        (6, "security", "CWE-89")
    ]
    assert result["stats"]["live_calls"] == 3  # one call per agent, no supervisor for 1 file
    assert result["stats"]["input_tokens"] == 300
    assert first["metrics"]["all"]["overall"]["f1"] == 1.0
    assert first["run"]["prompt_versions"].startswith("security@")
    assert len(list((tmp_path / "cache").rglob("*.json"))) == 3

    calls_before = eval_env.calls
    second = await run_evaluation(config("replay"), [case], progress=lambda _: None)
    [replayed] = second["cases"]
    assert eval_env.calls == calls_before  # the model was not called again
    assert replayed["stats"]["cached_calls"] == 3 and replayed["stats"]["live_calls"] == 0
    assert replayed["findings"] == result["findings"]
    assert second["metrics"]["all"]["latency"]["live_cases"] == 0


async def test_replay_fails_when_an_answer_was_never_recorded(eval_env, case):
    document = await run_evaluation(config("replay"), [case], progress=lambda _: None)
    [result] = document["cases"]
    assert result["status"] == "error"
    assert "without a recorded answer" in result["error"]
    assert document["metrics"]["all"]["cases_failed"] == 1


async def test_changed_prompt_misses_the_cache(eval_env, case, tmp_path):
    await run_evaluation(config("use"), [case], progress=lambda _: None)
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    from app.graph.prompts import PROMPT_NAMES, get_prompt

    for name in PROMPT_NAMES:
        prompt = get_prompt(name)
        text = prompt.text + ("\nBe thorough." if name == "security" else "")
        (prompts / f"{name}.md").write_text(f"---\nversion: 2\n---\n{text}\n", encoding="utf-8")
    changed = config("use")
    changed.prompts_dir = str(prompts)
    document = await run_evaluation(changed, [case], progress=lambda _: None)
    stats = document["cases"][0]["stats"]
    assert (stats["live_calls"], stats["cached_calls"]) == (1, 2)  # only the security agent


def test_prune_keeps_only_the_answers_used(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    from evals.llm_cache import DiskCache

    cache = DiskCache(tmp_path)
    folder = tmp_path / cache.model_dir_name()
    folder.mkdir()
    (folder / "used.json").write_text("{}")
    (folder / "stale.json").write_text("{}")
    cache.used_keys.add("used")
    assert cache.prune() == 1
    assert [p.name for p in folder.iterdir()] == ["used.json"]


# --- CI gate -------------------------------------------------------------------


def results_file(tmp_path: Path, f1: float, failed: int = 0, fingerprint: str = "abc") -> str:
    document = {
        "run": {
            "id": "run",
            "model": "m",
            "prompt_versions": "security@1",
            "dataset_fingerprint": fingerprint,
        },
        "metrics": {
            "all": {
                "cases_failed": failed,
                "overall": {"precision": 0.5, "recall": 0.5, "f1": f1},
                "clean_flagged_rate": 0.5,
            }
        },
    }
    path = tmp_path / f"results-{f1}-{failed}-{fingerprint}.json"
    path.write_text(json.dumps(document))
    return str(path)


@pytest.fixture
def baseline(tmp_path, monkeypatch) -> str:
    path = tmp_path / "baseline.json"
    monkeypatch.setattr(cli, "BASELINE_PATH", path)
    cli.cmd_baseline(argparse.Namespace(results=results_file(tmp_path, 0.5), max_f1_drop=0.03))
    return str(path)


def test_gate_passes_within_the_allowed_drop(tmp_path, baseline, capsys):
    cli.cmd_gate(argparse.Namespace(results=results_file(tmp_path, 0.48), baseline=baseline))
    assert "Regression gate passed" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("f1", "failed", "fingerprint", "reason"),
    [
        (0.46, 0, "abc", "F1 dropped"),
        (0.6, 2, "abc", "could not be evaluated"),
        (0.6, 0, "changed", "smoke dataset changed"),
    ],
)
def test_gate_fails(tmp_path, baseline, capsys, f1, failed, fingerprint, reason):
    with pytest.raises(SystemExit):
        cli.cmd_gate(
            argparse.Namespace(
                results=results_file(tmp_path, f1, failed, fingerprint), baseline=baseline
            )
        )
    assert reason in capsys.readouterr().out
