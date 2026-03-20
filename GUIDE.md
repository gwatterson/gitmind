# GUIDE.md — GitMind Testing Guide

Complete step-by-step guide to set up, configure, and test the GitMind Autonomous Code Review Agent.

---

## 1. Prerequisites

Before starting, ensure you have installed:

- **Python 3.11+** → [python.org/downloads](https://www.python.org/downloads/)
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
   - **Webhook Secret**: Generate a random string (e.g., use `python -c "import secrets; print(secrets.token_hex(32))"`)
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

### 2.4 LangSmith (optional — for tracing)

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

## 3. Create a Test Repository on GitHub

Create a public repo called `test-vulnerable-app` with intentionally problematic code for testing:

### 3.1 Create the repo

1. Go to [github.com/new](https://github.com/new)
2. Name: `test-vulnerable-app`
3. Set to **Public**
4. Initialize with a README
5. Click **Create repository**

### 3.2 Add test files on `main` branch

Create these files with intentional issues:

**`vulnerable_app.py`** — Security issues:
```python
import sqlite3

def login(username, password):
    conn = sqlite3.connect("users.db")
    # SQL INJECTION: user input directly in query
    query = f"SELECT * FROM users WHERE username='{username}' AND password='{password}'"
    result = conn.execute(query)
    return result.fetchone()

API_KEY = "sk-1234567890abcdef"  # HARDCODED SECRET

def render_page(user_input):
    # XSS: user input directly in HTML
    return f"<html><body>Welcome {user_input}</body></html>"
```

**`complex_logic.py`** — Quality issues:
```python
def process_data(data, flag1, flag2, flag3, mode, extra):
    if flag1:
        if data:
            if flag2:
                if mode == "a":
                    if flag3:
                        if extra:
                            for item in data:
                                if item > 0:
                                    if item < 100:
                                        result = item * 2
                                    else:
                                        result = item
                                else:
                                    result = 0
                        else:
                            result = -1
                    else:
                        result = -2
                elif mode == "b":
                    result = sum(data)
                else:
                    result = 0
            else:
                result = len(data)
        else:
            result = None
    else:
        result = False
    return result
```

**`slow_code.py`** — Performance issues:
```python
import time

def get_user_orders(db, user_ids):
    # N+1 QUERY: querying inside a loop
    orders = []
    for uid in user_ids:
        user = db.query(f"SELECT * FROM users WHERE id = {uid}")
        user_orders = db.query(f"SELECT * FROM orders WHERE user_id = {uid}")
        orders.append({"user": user, "orders": user_orders})
    return orders

def build_report(items):
    # STRING CONCATENATION IN LOOP
    report = ""
    for item in items:
        report += f"Item: {item['name']}, Price: {item['price']}\n"
    return report
```

### 3.3 Create a Pull Request for testing

1. Create a new branch: `feature/add-payment`
2. Add/modify some files on that branch
3. Open a PR from `feature/add-payment` → `main`
4. Note the **PR number** (e.g., `#1`)

---

## 4. Setup & Configuration

### 4.1 Backend setup

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate it (Windows)
venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Copy and fill in environment variables
copy .env.example .env
# Edit .env with your actual values (see Section 2)
```

### 4.2 Frontend setup

```bash
cd frontend

# Install dependencies
npm install

# Copy env file
copy .env.local.example .env.local
# The default value (http://localhost:8000) should work for local dev
```

---

## 5. Running the Application

### 5.1 Quick start (recommended)

Simply run the start script from the project root:

```bash
start.bat
```

This will:
1. Create and activate the Python virtual environment
2. Install backend dependencies
3. Start the FastAPI backend on port 8000
4. Start the Next.js frontend on port 3000
5. Open the dashboard in your browser

### 5.2 Manual start

**Terminal 1 — Backend:**
```bash
cd backend
venv\Scripts\activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm run dev
```

**Terminal 3 — ngrok (for testin webhooks locally):**
```bash
ngrok http 8000
```
Then update your GitHub App's webhook URL with the ngrok URL.

---

## 6. Testing the Application

### 6.1 Verify backend is running

Open: [http://localhost:8000/api/health](http://localhost:8000/api/health)

Expected response:
```json
{
  "status": "ok",
  "llm_model": "gemini-2.5-flash",
  "rate_limiter": { "rpm_used": 0, "rpm_max": 120 },
  "hitl_enabled": false
}
```

### 6.2 Verify frontend is running

Open: [http://localhost:3000](http://localhost:3000)

You should see the GitMind dashboard with metrics and the manual review trigger form.

### 6.3 Trigger a manual review (no webhook needed)

1. Open the dashboard at `http://localhost:3000`
2. In the **"Manual Review"** panel on the right, enter:
   - **Repo**: `your-username/test-vulnerable-app`
   - **PR number**: The PR number you created (e.g., `1`)
3. Click **"🚀 Trigger Review"**
4. Watch the review appear in the PR list
5. Click on it to see the **reasoning trace streaming** in real-time
6. Wait for the review to complete — you should see security, quality, and performance findings

### 6.4 Trigger via webhook (full integration)

1. Start ngrok: `ngrok http 8000`
2. Update your GitHub App's webhook URL to the ngrok URL (e.g., `https://abc123.ngrok.io/webhook/github`)
3. Open a new PR or push to an existing PR in your test repo
4. The webhook will fire automatically and trigger a review
5. Check the dashboard — a new review should appear

### 6.5 Run backend tests

```bash
cd backend
venv\Scripts\activate
pytest tests/ -v
```

### 6.6 API Explorer

FastAPI auto-generates interactive API docs:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 7. Troubleshooting

| Problem | Solution |
|---|---|
| `GEMINI_API_KEY` error | Verify your key at [aistudio.google.com](https://aistudio.google.com/apikey) |
| `GitHub client not configured` | Set either `GITHUB_TOKEN` or GitHub App credentials in `.env` |
| Frontend can't reach backend | Check `NEXT_PUBLIC_API_URL` in `frontend/.env.local` |
| Rate limiter blocking too early | Adjust `RATE_LIMIT_*` values in `.env` to match your tier |
| Webhook not firing | Verify ngrok is running and GitHub App webhook URL is updated |
| `semgrep not found` | Semgrep has limited Windows support; the app works without it |

---

*End of testing guide — GUIDE.md v1.0*
