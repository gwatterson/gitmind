# Evaluation run 20260929-164817-verifier-gemini-probe

- Pipeline: GitMind with qwen2.5-coder:7b (ollama)
- Split: `all`, 4 cases, dataset `5f5ac554a08b`, filters {'case': ['cve-asyncssh-scp-traversal', 'cve-danger-path-injection', 'oss-hono-5376', 'syn-py-clean-safe-patterns']}
- Prompts: `security@2,quality@2,performance@2,agent_rules@2,verifier@1,supervisor@1,synthesis@1`
- Code revision: `e1565f7+dirty`, cache mode `use`
- Matching: same file and category, line within 3 of the expected range

## Headline

| Metric | All findings | Severity >= medium |
|---|---|---|
| Precision | 0.25 | 0.29 |
| Recall | 1.00 | 1.00 |
| F1 | 0.40 | 0.44 |
| Localization recall (any category) | 1.00 | 1.00 |
| Line inside expected range | 1.00 | 1.00 |
| CWE accuracy (matched security findings) | 1.00 | 1.00 |
| Clean PRs with at least one finding | 0.50 | 0.50 |
| Findings per clean PR | 3 | 2.5 |
| Unsafe PRs blocked (request changes) | n/a | n/a |
| Clean PRs blocked | 0.00 | 0.00 |
| Findings on must-not-flag lines | 3 | 3 |

## Verifier threshold

Metrics replayed from the recorded verifier answers (0.0 keeps every finding).

| Threshold | Precision | Recall | F1 | Findings per clean PR |
|---|---|---|---|---|
| 0.0 | 0.25 | 1.00 | 0.40 | 3 |
| 0.3 | 0.25 | 1.00 | 0.40 | 3 |
| 0.4 | 0.25 | 1.00 | 0.40 | 3 |
| 0.5 | 0.25 | 1.00 | 0.40 | 3 |
| 0.6 | 0.25 | 1.00 | 0.40 | 3 |
| 0.7 | 0.25 | 1.00 | 0.40 | 3 |
| 0.8 | 0.25 | 1.00 | 0.40 | 3 |
| 0.9 | 0.25 | 1.00 | 0.40 | 3 |

## By category

| Category | Expected | Found | False pos. | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| performance | 0 | 0 | 1 | 0.00 | n/a | n/a |
| quality | 0 | 0 | 3 | 0.00 | n/a | n/a |
| security | 2 | 2 | 2 | 0.50 | 1.00 | 0.67 |

## By source

| Source | Expected | Found | False pos. | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| cve | 2 | 2 | 0 | 1.00 | 1.00 | 1.00 |
| oss | 0 | 0 | 0 | n/a | n/a | n/a |
| synthetic | 0 | 0 | 6 | 0.00 | n/a | n/a |

## By language

| Language | Expected | Found | False pos. | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| python | 1 | 1 | 6 | 0.14 | 1.00 | 0.25 |
| typescript | 1 | 1 | 0 | 1.00 | 1.00 | 1.00 |

## Cost and latency

|  | Value |
|---|---|
| Cases measured live | 0 |
| Wall time per review p50 / p95 (s) | n/a / n/a |
| LLM calls per review | 4 |
| Input / output tokens per review | 4124 / 1961 |
| Live / replayed calls | 4 / 12 |

## Cases

| Case | Source | Found | False pos. | Verdict | Status |
|---|---|---|---|---|---|
| `cve-asyncssh-scp-traversal` | cve | 1/1 | 0 | request_changes | ok |
| `cve-danger-path-injection` | cve | 1/1 | 0 | request_changes | ok |
| `oss-hono-5376` | oss | 0/0 | 0 | approve | ok |
| `syn-py-clean-safe-patterns` | synthetic | 0/0 | 6 | comment | ok |
