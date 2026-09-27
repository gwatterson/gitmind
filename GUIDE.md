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

### 2.4 Dashboard authentication

The dashboard and every `/api/*` endpoint (except `/api/health`) require authentication.
There are two ways to run GitMind:

| Mode | When to use it | Setting |
|---|---|---|
| Sign-in disabled | Local development on your own machine | `AUTH_DISABLED=true` |
| GitHub sign-in | Anything reachable by other people | `AUTH_DISABLED=false` plus a GitHub OAuth App |

#### Option A: local development without sign-in

Add to `backend/.env`:

```
AUTH_DISABLED=true
```

Every request is treated as an administrator, the dashboard shows an **"Auth disabled"**
badge next to the user `local-dev`, and API keys are not checked (there is nothing to
check them against). The backend refuses to start with this setting when
`ENVIRONMENT=production`.

#### Option B: GitHub sign-in

1. Go to [GitHub Developer Settings → OAuth Apps](https://github.com/settings/developers) and click **"New OAuth App"**.
2. Fill in:
   - **Application name**: e.g. `GitMind (local)`
   - **Homepage URL**: `http://localhost:3000`
   - **Authorization callback URL**: `http://localhost:8000/auth/callback`

   An OAuth App accepts a single callback URL, so create a separate one for each
   environment (local, production).
3. Click **"Register application"**, then **"Generate a new client secret"** and copy it
   immediately: GitHub shows it only once.
4. Generate a session secret and copy the printed value:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```
5. Update `backend/.env` (replace the placeholders with your values):
   ```
   AUTH_DISABLED=false
   GITHUB_OAUTH_CLIENT_ID=your_client_id
   GITHUB_OAUTH_CLIENT_SECRET=your_client_secret
   AUTH_ALLOWED_USERS=your-github-login
   AUTH_ADMIN_USERS=your-github-login
   SESSION_SECRET=the_value_printed_in_step_4
   ```
   The defaults `PUBLIC_API_URL=http://localhost:8000`, `FRONTEND_URL=http://localhost:3000`
   and `CORS_ORIGINS=http://localhost:3000` already match a local setup.
6. Restart the backend: settings are read only at startup.
7. Open [http://localhost:3000](http://localhost:3000), click **"Sign in with GitHub"** and
   authorize the app. GitHub asks for the `read:user` and `read:org` scopes. You land back on
   the dashboard with your login in the navigation bar (and an `admin` label if you are listed
   in `AUTH_ADMIN_USERS`).

**Who can sign in**
- `AUTH_ALLOWED_USERS`: comma-separated GitHub logins (case-insensitive).
- `AUTH_ALLOWED_ORGS`: comma-separated organizations; any member can sign in. Membership is
  read at sign-in time. If the organization restricts third-party OAuth applications, an
  organization owner must approve the app first, otherwise the membership is not visible
  and the sign-in is refused.
- `AUTH_ADMIN_USERS`: logins that can clear the archive and manage API keys. Administrators
  must also be allowed by one of the two lists above.
- The allowlists are re-checked on every request: removing a user or an organization from
  `.env` (and restarting) revokes access immediately, without waiting for the session to
  expire. A user who leaves an allowed organization keeps access until their session expires.

**Sessions**
- Sessions last `SESSION_TTL_HOURS` (default 168, one week); **"Sign out"** in the navigation bar ends them earlier.
- Changing `SESSION_SECRET` signs everybody out. If it is left empty in development, a random
  secret is generated at every backend start, so you have to sign in again after each restart.
- The GitHub access token is used once during sign-in and never stored.
- Use the same host name everywhere: open the dashboard at `http://localhost:3000` and keep
  `NEXT_PUBLIC_API_URL=http://localhost:8000`. Mixing `localhost` and `127.0.0.1` makes the
  browser treat them as different sites, and the session cookie is not sent.

#### API keys (scripts and CI)

API keys work only with GitHub sign-in enabled. An administrator creates them through the API:

1. Sign in to the dashboard, open the browser developer tools
   (Chrome: **Application → Cookies**, Firefox: **Storage → Cookies**, site `http://localhost:8000`) and copy the value of `gitmind_session`.
2. Create the key:
   ```bash
   curl -X POST http://localhost:8000/api/keys \
     -H "Content-Type: application/json" -H "X-Requested-With: gitmind" \
     --cookie "gitmind_session=PASTE_THE_COOKIE_VALUE" \
     -d '{"name": "ci", "scopes": ["reviews:read", "reviews:write"], "expires_in_days": 90}'
   ```
   The response contains the key (`gm_...`) **only once**: store it in a secret manager.
3. Use it as `Authorization: Bearer gm_...`. Requests with an API key do not need the
   `X-Requested-With` header.

| Field | Values |
|---|---|
| `scopes` | `reviews:read` (list and read reviews), `reviews:write` (trigger, approve, edit, delete). Default: `["reviews:read"]` |
| `expires_in_days` | 1 to 365, default 90; `null` for a key that never expires |

List keys with `GET /api/keys` and revoke one with `DELETE /api/keys/{id}` (same cookie and
headers as above). Revocation takes effect on the next request.

#### Production settings

With `ENVIRONMENT=production` the backend refuses to start unless all of these are set:
`AUTH_DISABLED=false`, `GITHUB_WEBHOOK_SECRET`, a `SESSION_SECRET` of at least 32 characters,
`GITHUB_OAUTH_CLIENT_ID` and `GITHUB_OAUTH_CLIENT_SECRET`, and at least one of
`AUTH_ALLOWED_USERS` or `AUTH_ALLOWED_ORGS`. In addition:
- The session cookie is marked `Secure`, so the backend must be served over HTTPS.
- Serve the dashboard and the API from the same site, for example `gitmind.example.com` and
  `api.gitmind.example.com`: the session cookie is not sent across different domains.
- Set `PUBLIC_API_URL`, `FRONTEND_URL`, `CORS_ORIGINS` (backend) and `NEXT_PUBLIC_API_URL`
  (frontend) to the public URLs, and use an OAuth App whose callback URL is
  `<PUBLIC_API_URL>/auth/callback`.
- The interactive API docs (`/docs`, `/redoc`) are disabled.

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

With `AUTH_DISABLED=true` you see the dashboard directly, with metrics and the manual review
trigger form. With GitHub sign-in enabled you first see the **"Sign in to GitMind"** screen
(see section 2.4). If that screen says that GitHub sign-in is not configured, the OAuth
settings are missing from `backend/.env`.

### 6.3 Trigger a manual review (no webhook needed)

1. Open the dashboard at `http://localhost:3000` (and sign in, if sign-in is enabled)
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
| "Your GitHub account is not on the list of allowed users" | Add your login to `AUTH_ALLOWED_USERS` (or your organization to `AUTH_ALLOWED_ORGS`) and restart the backend. For organizations, check that the OAuth App is approved by the organization |
| Sign-in succeeds but the dashboard keeps showing the sign-in screen | The session cookie is not sent: use `localhost` (not `127.0.0.1`) for both the dashboard and `NEXT_PUBLIC_API_URL`, and check that `CORS_ORIGINS` contains the dashboard URL |
| You must sign in again after every backend restart | Set a fixed `SESSION_SECRET` in `backend/.env` |
| GitHub shows an error about the `redirect_uri` during sign-in | The OAuth App callback URL must be exactly `<PUBLIC_API_URL>/auth/callback` |
| Write actions fail with "Missing X-Requested-With header" | Scripts using the session cookie must send `X-Requested-With: gitmind`, or use an API key instead |
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
