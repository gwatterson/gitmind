# GitMind Testing Guide

Complete step-by-step guide to set up, configure, and test the GitMind Autonomous Code Review Agent.

---

## 1. Prerequisites

Before starting, ensure you have installed:

- **Python 3.11+** → [python.org/downloads](https://www.python.org/downloads/)
- **uv** (Python package manager) → `pip install uv` or see [docs.astral.sh/uv](https://docs.astral.sh/uv/)
- **Node.js 20+** → [nodejs.org](https://nodejs.org/)
- **Git** → [git-scm.com](https://git-scm.com/)
- **ngrok** (optional, for webhook testing) → [ngrok.com](https://ngrok.com/)

---

## 2. API Keys & Free Subscriptions

### 2.1 Google Gemini API Key (required)

1. Go to [Google AI Studio](https://aistudio.google.com/apikey)
2. Sign in with your Google account
3. Click **"Create API Key"**
4. Copy the key → this is your `GEMINI_API_KEY`
5. **Free tier** gives you ~20 requests/day and 250k tokens/minute
6. If `gemini-2.5-flash` is not available, use `gemini-2.0-flash` or whichever model is available. Update `GEMINI_MODEL` in your `.env` accordingly.

### 2.2 GitHub App (required for webhook integration)

1. Go to [GitHub Developer Settings](https://github.com/settings/apps)
2. Click **"New GitHub App"**
3. Fill in the form:
   - **Name**: `GitMind-YourName` (must be unique)
   - **Homepage URL**: `http://localhost:3000`
   - **Webhook URL**: `http://localhost:8000/webhook/github` (update with ngrok URL later)
   - **Webhook Secret**: Generate a random string (e.g., use `python -c "import secrets; print(secrets.token_hex(32))"`) and put the same value in `GITHUB_WEBHOOK_SECRET` in `backend/.env`. It is mandatory: deliveries without a valid signature are always rejected.
   - **Permissions**:
     - Repository: **Pull Requests** → Read & Write
     - Repository: **Contents** → Read
   - **Subscribe to events**: Pull Request
4. Click **"Create GitHub App"**
5. Note your **App ID** → this is `GITHUB_APP_ID`
6. Scroll down and click **"Generate a private key"** → download the `.pem` file
7. Save the `.pem` file to `backend/secrets/github_private_key.pem`
8. Update `GITHUB_PRIVATE_KEY_PATH` in `.env` to `./secrets/github_private_key.pem`
9. **Install the App** on your test repository:
   - Go to your GitHub App page → "Install App" → Select your test repo

### 2.3 Alternative: GitHub Personal Access Token (simpler, for testing only)

If you don't want to create a full GitHub App:
1. Go to [GitHub Tokens](https://github.com/settings/tokens?type=beta)
2. Create a **Fine-grained token** with:
   - **Repository access**: Select your test repo
   - **Permissions**: Pull Requests (Read & Write), Contents (Read)
3. Copy the token
4. Add `GITHUB_TOKEN=ghp_your_token_here` to your `backend/.env` file
5. The app will use this token as a fallback when GitHub App credentials are not configured

### 2.4 GitHub OAuth App (required for dashboard sign-in)

The dashboard and the API are protected: users sign in with GitHub and only the
accounts or organizations you allow can access them.

1. Go to [GitHub Developer Settings → OAuth Apps](https://github.com/settings/developers) and click **"New OAuth App"**
2. Fill in:
   - **Homepage URL**: `http://localhost:3000`
   - **Authorization callback URL**: `http://localhost:8000/auth/callback`
3. Click **"Register application"**, then **"Generate a new client secret"**
4. Set in `backend/.env`:
   ```
   GITHUB_OAUTH_CLIENT_ID=your_client_id
   GITHUB_OAUTH_CLIENT_SECRET=your_client_secret
   AUTH_ALLOWED_USERS=your-github-login
   AUTH_ADMIN_USERS=your-github-login
   SESSION_SECRET=<python -c "import secrets; print(secrets.token_urlsafe(48))">
   ```

For quick local experiments you can skip this step with `AUTH_DISABLED=true`: every
request is then treated as an administrator, and the dashboard shows an
"Auth disabled" badge. The backend refuses this setting when `ENVIRONMENT=production`.

**API keys** for scripts and CI can be created by an administrator:

```bash
curl -X POST http://localhost:8000/api/keys \
  -H "Content-Type: application/json" -H "X-Requested-With: gitmind" \
  --cookie "gitmind_session=<your session cookie>" \
  -d '{"name": "ci", "scopes": ["reviews:read", "reviews:write"], "expires_in_days": 90}'
```

The key is shown only once; send it as `Authorization: Bearer gm_...`.

### 2.5 LangSmith (optional, for tracing)

1. Go to [smith.langchain.com](https://smith.langchain.com/)
2. Sign up (free tier: 5,000 traces/month)
3. Create an API key
4. Set in `.env`:
   ```
   LANGSMITH_API_KEY=your_key
   LANGSMITH_TRACING=true
   LANGCHAIN_PROJECT=code-review-agent
   ```

---

## 3. Create a Pull Request for testing

1. Create a new branch: `feature/add-payment`
2. Add/modify some files on that branch
3. Open a PR from `feature/add-payment` → `main`
4. Note the **PR number** (e.g., `#1`)

---

## 4. Setup & Configuration

### 4.1 Backend setup

```bash
cd backend

# Create the virtual environment (.venv) and install the locked dependencies,
# including the dev tools (pytest, ruff, mypy, pre-commit)
uv sync

# Copy and fill in environment variables
# On Windows:
copy .env.example .env
# On Mac/Linux:
cp .env.example .env
# Edit .env with your actual values (see Section 2)
```

### 4.2 Frontend setup

```bash
cd frontend

# Install dependencies
npm install

# Copy env file
# On Windows:
copy .env.local.example .env.local
# On Mac/Linux:
cp .env.local.example .env.local
# The default value (http://localhost:8000) should work for local dev
```

---

## 5. Running the Application

### 5.1 Quick start (recommended)

Simply run the start script from the project root:

**On Windows:**
```bash
start.bat
```

**On Mac/Linux:**
```bash
chmod +x start.sh
./start.sh
```

This will:
1. Create the Python virtual environment and install the locked backend dependencies (`uv sync`)
2. Create `backend/.env` and `frontend/.env.local` from the templates if missing
3. Start the FastAPI backend on port 8000
4. Start the Next.js frontend on port 3000
5. Open the dashboard in your browser

### 5.2 Manual start

**Terminal 1 (backend):**
```bash
cd backend
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 (frontend):**
```bash
cd frontend
npm run dev
```

**Terminal 3 (ngrok, for testing webhooks locally):**
```bash
ngrok http 8000
```
Then update your GitHub App's webhook URL with the ngrok URL.

---

## 6. Testing the Application

### 6.1 Verify backend is running

Open: [http://localhost:8000/api/health](http://localhost:8000/api/health)

Expected response (the health check is public and intentionally exposes no internal state):
```json
{ "status": "ok" }
```

Every other `/api/*` endpoint requires authentication and returns `401` without a session.

### 6.2 Verify frontend is running

Open: [http://localhost:3000](http://localhost:3000)

You should see the GitMind dashboard with metrics and the manual review trigger form.

### 6.3 Trigger a manual review (no webhook needed)

1. Open the dashboard at `http://localhost:3000`
2. In the **"Manual Review"** panel on the right, enter:
   - **Repo**: `your-username/test-vulnerable-app`
   - **PR number**: The PR number you created (e.g., `1`)
3. Click **"Trigger Review"**
4. Watch the review appear in the PR list
5. Click on it to see the **reasoning trace streaming** in real-time
6. Wait for the review to complete: you should see security, quality, and performance findings

### 6.4 Trigger via webhook (full integration)

1. Start ngrok: `ngrok http 8000`
2. Update your GitHub App's webhook URL to the ngrok URL (e.g., `https://abc123.ngrok.io/webhook/github`)
3. Open a new PR or push to an existing PR in your test repo
4. The webhook will fire automatically and trigger a review
5. Check the dashboard: a new review should appear

### 6.5 Run tests and quality checks

Tests run against a temporary database and never call external services.

```bash
cd backend
uv run pytest --cov          # tests with coverage report
uv run ruff check .          # lint
uv run ruff format --check . # formatting
uv run mypy                  # type checking
```

```bash
cd frontend
npm run lint
npx tsc --noEmit
```

To run all checks automatically before every commit, install the git hooks once
(from the repository root):

```bash
uv run --project backend pre-commit install
```

The same checks run in GitHub Actions on every push and pull request (see `.github/workflows/`).

### 6.6 API Explorer

FastAPI auto-generates interactive API docs:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 7. Troubleshooting

| Problem | Solution |
|---|---|
| `GEMINI_API_KEY` error | Verify your key at [aistudio.google.com](https://aistudio.google.com/apikey) |
| Sign-in page says GitHub sign-in is not configured | Create the OAuth App (section 2.4), or set `AUTH_DISABLED=true` for local development |
| "Your GitHub account is not on the list of allowed users" | Add your login to `AUTH_ALLOWED_USERS` (or your organization to `AUTH_ALLOWED_ORGS`) |
| Webhook deliveries fail with 401 | `GITHUB_WEBHOOK_SECRET` must be set and identical to the secret configured on GitHub |
| Backend refuses to start with "Insecure production configuration" | With `ENVIRONMENT=production` all security settings are mandatory: the error lists the missing ones |
| Review status "Quota Exhausted" | The daily LLM quota is used up: trigger the review again after the reset |
| `GitHub client not configured` | Set either `GITHUB_TOKEN` or GitHub App credentials in `.env` |
| Frontend can't reach backend | Check `NEXT_PUBLIC_API_URL` in `frontend/.env.local` |
| Rate limiter blocking too early | Adjust `RATE_LIMIT_*` values in `.env` to match your tier |
| Webhook not firing | Verify ngrok is running and GitHub App webhook URL is updated |
| `semgrep not found` | Semgrep has limited Windows support; the app works without it |

---

*End of testing guide (GUIDE.md v1.0)*
