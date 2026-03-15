# Test Files — Intentionally Vulnerable Code

This folder contains sample Python files with **intentional** security, quality, and performance issues. They are used to test and demonstrate GitMind's code review capabilities.

## Files

| File | Agent | Issues |
|---|---|---|
| `vulnerable_app.py` | Security | SQL injection, hardcoded secrets, XSS |
| `complex_logic.py` | Quality | Cyclomatic complexity > 15, poor naming, too many params |
| `slow_code.py` | Performance | N+1 queries, string concat in loops, blocking I/O |

## How to Use

### Option A: Local testing with manual trigger

1. Push these files to a GitHub repository (e.g., `test-vulnerable-app`)
2. Create a PR that adds or modifies these files
3. Use the GitMind dashboard's **Manual Review** panel:
   - **Repo**: `your-username/test-vulnerable-app`
   - **PR number**: the PR number
4. Click **🚀 Trigger Review** and watch the analysis

### Option B: Webhook-based testing

1. Install the GitMind GitHub App on your test repository
2. Open a PR containing these files
3. The webhook fires automatically and triggers a review

## Expected Results

- **Security agent**: Should flag SQL injection, hardcoded API key, and XSS
- **Quality agent**: Should flag high complexity, poor naming, too many parameters
- **Performance agent**: Should flag N+1 queries, string concatenation, and blocking I/O
