"""Run the real review pipeline on the evaluation cases.

The graph is the production one without delivery (no summary call, no human
approval, no GitHub): supervisor, the three agents and the deterministic part of
the synthesis (validation, deduplication, verdict). Each case gets a review row
in a throwaway SQLite database, because the nodes record their progress there.
"""

import asyncio
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langchain_core.globals import set_llm_cache

from app.config import settings
from app.db import crud, models
from app.graph.graph import build_graph, initial_state
from app.graph.prompts import PROMPT_NAMES, get_prompt, prompt_versions
from app.llm import factory
from app.rate_limiter import DailyQuotaExhaustedError
from evals.dataset import EVAL_DIR, Case, dataset_fingerprint
from evals.llm_cache import CacheMode, CallStats, DiskCache, track_calls
from evals.matching import LINE_TOLERANCE
from evals.metrics import compute_metrics, verifier_curve

CACHE_DIR = EVAL_DIR / "cache"
RESULTS_DIR = EVAL_DIR / "results"

FINDING_FIELDS = (
    "file",
    "line",
    "severity",
    "category",
    "rule_id",
    "cwe",
    "confidence",
    "agent",
    "verifier_confidence",
    "verifier_real",
)


@dataclass
class RunConfig:
    provider: str
    model: str
    split: str = "dev"
    cache_mode: CacheMode = "use"
    concurrency: int = 1
    timeout_seconds: float = 600.0
    prompts_dir: str = ""
    verifier: bool = True
    verifier_provider: str = ""
    label: str = ""
    filters: dict[str, Any] = field(default_factory=dict)


def git_revision() -> str:
    """Short commit of the code under evaluation, with '+dirty' for uncommitted changes."""
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--", "backend/app"],
            capture_output=True,
            text=True,
            check=True,
            cwd=EVAL_DIR.parent,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return f"{commit}+dirty" if dirty else commit


def configure(config: RunConfig, database_path: Path) -> DiskCache:
    """Point the app at the evaluation settings. Must run before the first review."""
    settings.LLM_PROVIDER = config.provider  # type: ignore[assignment]
    if config.provider == "ollama":
        settings.OLLAMA_MODEL = config.model
    else:
        settings.GEMINI_MODEL = config.model
    settings.HITL_ENABLED = False
    settings.LLM_TIMEOUT_SECONDS = config.timeout_seconds
    settings.PROMPTS_DIR = config.prompts_dir
    settings.VERIFIER_ENABLED = config.verifier
    settings.VERIFIER_PROVIDER = config.verifier_provider  # type: ignore[assignment]
    factory.reset_runtime_provider()
    models.DATABASE_PATH = str(database_path)

    cache = DiskCache(CACHE_DIR, config.cache_mode)
    set_llm_cache(cache)
    return cache


def _finding(raw: dict[str, Any]) -> dict[str, Any]:
    finding = {key: raw.get(key) for key in FINDING_FIELDS}
    finding["message"] = str(raw.get("message", ""))[:400]
    finding["evidence"] = str(raw.get("evidence", ""))[:300]
    return finding


async def run_case(case: Case, graph: Any) -> dict[str, Any]:
    stats = CallStats()
    review = await crud.create_review(repo=f"eval/{case.id}", pr_number=1, pr_title=case.title)
    # Only the title and the diff reach the model: the case id and description do not
    state = initial_state(
        review_id=review["id"],
        repo="eval/case",
        pr_number=1,
        commit_id="eval",
        files=case.files,
        pr_metadata={"title": case.title},
    )
    status, error = "ok", None
    final: dict[str, Any] = {}
    start = time.monotonic()
    try:
        with track_calls(stats):
            final = await graph.ainvoke(state)
    except DailyQuotaExhaustedError:
        raise
    except Exception as e:
        status, error = "error", f"{type(e).__name__}: {str(e)[:300]}"
    wall_seconds = time.monotonic() - start

    if stats.missing_calls:
        status, error = "error", f"{stats.missing_calls} call(s) without a recorded answer"
    elif final.get("status") == "failed":
        status, error = "error", "every agent failed"

    return {
        "case": case.model_dump(mode="json"),
        "status": status,
        "error": error,
        "agent_errors": list(final.get("errors", [])),
        "verdict": final.get("verdict", ""),
        "findings": [_finding(dict(f)) for f in final.get("all_findings", [])],
        "suppressed": [_finding(dict(f)) for f in final.get("suppressed_findings", [])],
        "files": [f["filename"] for f in case.files],
        "wall_seconds": round(wall_seconds, 2),
        "stats": asdict(stats),
    }


def run_metadata(config: RunConfig, cases: list[Case], pipeline: str) -> dict[str, Any]:
    created = datetime.now(UTC)
    label = config.label or f"{pipeline}-{config.model}".replace(":", "-").replace("/", "-")
    prompts = {
        name: {"version": get_prompt(name).version, "sha": get_prompt(name).sha}
        for name in PROMPT_NAMES
    }
    return {
        "id": f"{created:%Y%m%d-%H%M%S}-{label}",
        "label": label,
        "created_at": created.isoformat(timespec="seconds"),
        "pipeline": pipeline,
        "provider": config.provider,
        "model": config.model,
        "prompt_versions": prompt_versions() if pipeline == "gitmind" else None,
        "prompts": prompts if pipeline == "gitmind" else None,
        "prompts_dir": config.prompts_dir or None,
        "split": config.split,
        "filters": config.filters,
        "cases": len(cases),
        "dataset_fingerprint": dataset_fingerprint(cases),
        "code_revision": git_revision(),
        "cache_mode": config.cache_mode,
        "line_tolerance": LINE_TOLERANCE,
        "verifier": {
            "enabled": settings.VERIFIER_ENABLED,
            "min_confidence": settings.VERIFIER_MIN_CONFIDENCE,
            "provider": settings.VERIFIER_PROVIDER or config.provider,
        }
        if pipeline == "gitmind"
        else None,
    }


def build_document(meta: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "run": meta,
        "metrics": {
            "all": compute_metrics(results, "info").to_dict(),
            "medium_plus": compute_metrics(results, "medium").to_dict(),
            "verifier_curve": verifier_curve(results),
        },
        "cases": results,
    }


async def run_evaluation(
    config: RunConfig,
    cases: list[Case],
    *,
    prune_cache: bool = False,
    progress: Any = print,
) -> dict[str, Any]:
    """Run every case through the pipeline and return the results document."""
    with tempfile.TemporaryDirectory(prefix="gitmind-eval-") as tmp:
        cache = configure(config, Path(tmp) / "eval.db")
        await models.init_db()
        meta = run_metadata(config, cases, pipeline="gitmind")
        graph = build_graph(deliver=False)
        semaphore = asyncio.Semaphore(max(config.concurrency, 1))
        done = 0

        async def guarded(case: Case) -> dict[str, Any]:
            nonlocal done
            async with semaphore:
                result = await run_case(case, graph)
            done += 1
            stats = result["stats"]
            progress(
                f"[{done}/{len(cases)}] {case.id}: {result['status']}, "
                f"{len(result['findings'])} finding(s), verdict {result['verdict'] or '-'}, "
                f"{result['wall_seconds']:.0f}s ({stats['live_calls']} live, "
                f"{stats['cached_calls']} cached call(s))"
                + (f" [{result['error']}]" if result["error"] else "")
            )
            return result

        results = await asyncio.gather(*(guarded(case) for case in cases))
        if prune_cache:
            removed = cache.prune()
            progress(f"Removed {removed} unused cached answer(s).")
    return build_document(meta, list(results))
