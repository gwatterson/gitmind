# ADR 0001: verifier node, measured and disabled by default

Status: accepted, 2026-09-29

## Context

The evaluation (eval/README.md) showed that the review agents find most real problems
(recall 0.92 on the test split) but report many false alarms (about 5 per clean pull
request), and that the confidence they report does not separate the two. PLAN.md F8.5
proposed a verifier: a second LLM pass that re-reads the diff and suppresses the findings
the code does not support.

## Decision

The verifier is implemented as a graph node between the agents and the synthesis (one
call per file, fail-open, suppressed findings stored for analysis and never published),
and measured with `python -m evals run --verifier on`. With the same local model as the
agents (`qwen2.5-coder:7b`) it is **disabled by default** (`VERIFIER_ENABLED=false`).

| Split | | Findings per clean PR | Recall | F1 |
|---|---|---|---|---|
| dev | without verifier | 4.9 | 0.84 | 0.29 |
| dev | with verifier | 2.1 | 0.36 | 0.22 |
| test | without verifier | 5.2 | 0.92 | 0.30 |
| test | with verifier | 2.5 | 0.43 | 0.25 |

The verifier halves the noise but discards more than half of the real problems. The
threshold curve replayed on the dev split has its best F1 at threshold 0 (verifier off),
so no threshold is adopted. The model also answers "not real" with high confidence on
findings that are real: like the agents, a 7B model does not calibrate its judgments,
and checking its own findings adds little information.

## Update: a different model for the verifier

`VERIFIER_PROVIDER` routes the verifier calls to another provider while the agents keep
theirs (the evaluation cache and the rate limiter follow the provider of each call). A
first probe, limited by the free Gemini quota to four cases (two reversed CVEs, a clean
synthetic change that looks risky, a clean open source pull request), with the agents on
`qwen2.5-coder:7b`:

| Verifier | Real problems found | False positives |
|---|---|---|
| none | 2/2 | 16 |
| `qwen2.5-coder:7b` | 1/2 | 7 |
| `gemini-2.5-flash` | 2/2 | 6 |

This supports the hypothesis that the verifier needs a model different from, and more
capable than, the agents. Four cases are not enough to change the default: the decision
waits for the dev and test splits with `--verifier-provider gemini`.

## Consequences

- The node, its prompt (`verifier.md`), the suppressed findings in the database and the
  evaluation support stay in place, tested, behind the setting.
- Next measurement: the verifier on a different, more capable model than the agents
  (per-node model routing, PLAN.md F8.8), which also avoids self-confirmation. With a
  paid API this needs an explicit cost decision.
