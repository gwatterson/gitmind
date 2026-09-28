# GitMind evaluation

This directory measures how well the review pipeline finds real problems, how often it
raises false alarms, and what it costs. The same harness runs on every change that can
affect review quality (prompts, agents, models), so improvements and regressions show up
as numbers instead of impressions.

```
eval/
  dataset/cases/<case-id>/   one pull request per case: case.yaml + before/ + after/
  dataset/SOURCES.md         origin and license of every real-world case
  cache/                     recorded model answers (replayed for free, used by the CI gate)
  results/                   results (JSON) and reports (markdown) of the runs
  baseline.json              reference metrics of the CI regression gate
```

The code lives in [`backend/evals`](../backend/evals).

## Dataset

| Source | Cases | What it measures |
|---|---|---|
| Synthetic | 46 | One planted problem per case (SQL injection, SSRF, N+1 queries, swallowed exceptions, ...), plus hard negatives: safe code that looks risky |
| Reversed CVE fixes | 33 | Real vulnerabilities from the GitHub Advisory Database: the upstream fix is reversed, so the change reintroduces the bug |
| Open source pull requests | 22 | Merged pull requests of mature projects (click, httpx, starlette, rich, axios, hono, zod, ky): every finding counts as a false positive |

Cases cover Python, JavaScript and TypeScript, and are split into `dev` (used while
changing prompts) and `test` (frozen, only used for the reported numbers), so that the
prompts are not tuned on the cases they are judged on. Eighteen `dev` cases form the `smoke`
subset replayed by the CI gate.

A case is a small repository snapshot before and after the pull request, and a
`case.yaml`:

```yaml
id: syn-py-sqli-search
split: dev
source: synthetic
language: python
title: Add user search to the repository   # the only metadata the model sees
description: Search builds the SQL query with an f-string from the search term.
expected_findings:
  - file: app/repositories/users.py
    anchor: query = f"SELECT id, email, name FROM users WHERE name LIKE   # or lines: [22, 23]
    span: 1
    category: security
    cwe: [CWE-89]
    severity_min: high
    description: User-controlled search term interpolated into the SQL query
must_not_flag:
  - file: app/repositories/users.py
    anchor: SELECT COUNT(*) FROM users WHERE active = ?
    reason: parameterized query with a constant
```

The diff given to the pipeline is generated from `before/` and `after/` in the format of
the GitHub API, so the pipeline runs exactly as it does on a webhook. Expected findings
point at code with an `anchor` (a fragment found on exactly one line) instead of a line
number, which keeps them readable and easy to check. `also` lists other places where the
same problem appears (the same unsafe call repeated in a file): a finding on any of them
detects the problem.

`uv run python -m evals check` validates every case: anchors resolve to one line, every
expected range is on a line the diff shows, CWE ids only on security findings.

### How the real-world cases were built

- **CVE cases.** Advisories with a single fix commit and a small, focused diff were selected
  from the GitHub Advisory Database (`python -m evals fetch commit <repo> <sha> <id> --reverse`).
  The fixed file is `before/`, the vulnerable one `after/`: the pull request under review is
  the one that introduces the vulnerability. Each diff was read by hand to write the
  expected findings; fixes that could not be verified from the diff were dropped, and so
  were projects without a permissive license. Titles are neutral ("Simplify SCP header
  parsing") so that they give no hint.
- **Open source pull requests.** Recent merged pull requests of mature, permissively
  licensed projects, with one to four changed source files and no dependency bumps
  (`python -m evals fetch pr <repo> <number> <id>`). Test and documentation files are left
  out.

## Running

From `backend/` (or with `make` from the repository root):

```bash
uv run python -m evals run --split dev                 # local model via Ollama, answers cached
uv run python -m evals run --split test --compare <results.json>
uv run python -m evals run --provider gemini --case syn-py-sqli-search
uv run python -m evals run --prompts-dir ../my-prompts  # try an alternative prompt set
uv run python -m evals semgrep --split all              # baseline: semgrep alone
uv run python -m evals report <results.json>            # recompute metrics and report
```

The runner executes the production LangGraph graph (supervisor, three agents, validation,
deduplication and verdict) without GitHub, the summary call and human approval. Every
model call goes through a disk cache installed as the LangChain cache: the key is the
provider, the model, the exact prompt and the structured output schema. Rerunning the same
configuration replays the recorded answers for free; changing a prompt, a schema or the
model misses the cache and calls the model again. `--cache replay` never calls the model
and fails on a missing answer.

Prompts are versioned files (`backend/app/graph/prompts/*.md`, version in the front
matter). Each run records the prompt versions and a hash of their text, the code revision
and a fingerprint of the dataset, so two results are comparable only when they say so.

## Metrics

A finding **matches** an expected finding when it is on the same file, at most 3 lines
outside the expected range, and has the same category. Matching is one to one; further
findings on an already matched problem are counted as duplicates, not as false positives.

| Metric | Definition |
|---|---|
| Precision | matched findings / (matched + false positives), over every case |
| Recall | expected findings matched / expected findings |
| F1 | harmonic mean of precision and recall |
| Localization recall | expected findings with a finding at the right place, in any category |
| Line inside expected range | matched findings whose line is inside the range (distance 0) |
| CWE accuracy | matched security findings with one of the accepted CWE ids |
| Clean PRs flagged | cases without expected findings that received at least one finding |
| Unsafe PRs blocked | cases with a high or critical expected finding that got `request_changes` |
| Clean PRs blocked | clean cases that got `request_changes` |
| Must-not-flag hits | findings on lines marked as safe |

Metrics are reported for all findings and for findings of severity medium or above, and
broken down by category, source and language. Latency is the wall time of a review,
measured only on cases whose answers were all generated live.

## CI regression gate

`.github/workflows/eval.yml` runs on pull requests that touch the pipeline, the prompts or
the evaluation. It replays the smoke subset from `eval/cache` and fails when F1 drops more
than 3 points below `baseline.json`. A changed prompt misses the cache: record the new
answers locally with `uv run python -m evals run --smoke` and commit `eval/cache` together
with the prompt change. The replayed answers are the ones the new prompt actually
produced, so the gate cannot be satisfied with stale results, and CI needs neither a model
nor an API key.

To accept a new level of quality, update the baseline in the same pull request:
`uv run python -m evals baseline <smoke results.json>`.

## Limitations

- **Precision is a lower bound.** Real code (CVE cases, open source pull requests) can
  contain genuine problems nobody listed; they count as false positives.
- **Reversed fixes are easier than real pull requests.** The removed protective code is
  visible in the diff, which is a hint a real vulnerable pull request would not give.
- **One sample per configuration.** Local models are not deterministic across machines;
  the cache makes a run reproducible, not the model. Differences of a few points between
  two configurations are within noise on a dataset of this size.
- **Matching is lexical, not semantic.** A finding in the right place and category counts
  as a match even if its explanation is off; the CWE accuracy and the must-not-flag hits
  partly cover this. An LLM-as-judge for the explanation is not implemented.
