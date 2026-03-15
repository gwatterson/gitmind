# REQUIREMENTS.md — Autonomous Code Review Agent

> Complete specification document for application development.  
> Intended for: Claude Code, autonomous development agents, development teams.  
> Version: 1.0 — generated on 2026-03-13

---

## 1. Project overview

### 1.1 Description

An autonomous AI agent that automatically analyzes GitHub Pull Requests, identifying security vulnerabilities, code quality issues, and performance bottlenecks. The agent orchestrates specialized nodes via LangGraph, uses custom MCP tools to interact with GitHub, and posts structured inline comments directly on the PR. A web dashboard displays the reasoning trace in real-time streaming and aggregate metrics.

### 1.2 Goals

- Demonstrate a multi-agent architecture with LangGraph (supervisor/worker pattern)
- Expose a custom MCP server written from scratch (not a library wrapper)
- Integrate Gemini 2.5 Flash as the LLM via LangChain
- Implement a robust internal rate limiter with a safety margin
- Provide a UI with real-time streaming of the reasoning trace
- Be fully deployable using free/low-cost services

### 1.3 Intended use

Portfolio project for an AI Engineer role. The app must be technically solid, well documented, and demonstrable in a live 10-minute session.

---

## 2. Tech stack

### 2.1 Backend

| Component | Technology | Minimum version |
|---|---|---|
| Runtime | Python | 3.11+ |
| Web framework | FastAPI | 0.110+ |
| Agent orchestration | LangGraph | 0.2+ |
| LLM integration | LangChain + langchain-google-genai | latest |
| LLM model | Gemini 2.5 Flash (`gemini-2.5-flash`) | — |
| MCP server | Python MCP SDK (`mcp`) | 1.0+ |
| GitHub integration | PyGithub | 2.x |
| AST parsing | tree-sitter + tree-sitter-python/javascript | latest |
| Static analysis | semgrep (CLI subprocess) | latest OSS |
| Complexity metrics | radon | latest |
| HTTP client | httpx | latest |
| Data validation | pydantic v2 | 2.x |
| Task queue | native asyncio (no Celery for simplicity) | — |
| Tracing / observability | LangSmith | latest |
| Database | SQLite (via aiosqlite) for local persistence | — |
| Environment config | python-dotenv | latest |

### 2.2 Frontend

| Component | Technology |
|---|---|
| Framework | Next.js 14 (App Router) |
| Language | TypeScript |
| Styling | Tailwind CSS |
| UI components | shadcn/ui |
| Streaming | Server-Sent Events (SSE) |
| Data fetching | TanStack Query (react-query) |
| Diff viewer | react-diff-viewer-continued |
| Charts | Recharts |

### 2.3 Infrastructure

| Service | Use | Cost |
|---|---|---|
| GitHub App | Webhook + API access | Free |
| Vercel | Frontend hosting | Free tier |
| Railway or Render | Backend + MCP server hosting | Free tier |
| LangSmith | Tracing | Free tier (5k traces/month) |
| ngrok | Local tunnel during development | Free tier |

---

## 3. Architecture

### 3.1 Repository structure (monorepo)

```
autonomous-code-reviewer/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI entrypoint
│   │   ├── config.py                # Settings via pydantic-settings
│   │   ├── rate_limiter.py          # Internal rate limiter (CRITICAL)
│   │   ├── graph/
│   │   │   ├── state.py             # PRState TypedDict
│   │   │   ├── supervisor.py        # Supervisor node
│   │   │   ├── agents/
│   │   │   │   ├── security.py      # Security agent
│   │   │   │   ├── quality.py       # Quality agent
│   │   │   │   └── performance.py   # Performance agent
│   │   │   ├── synthesis.py         # Aggregation node
│   │   │   └── graph.py             # LangGraph graph construction
│   │   ├── mcp_server/
│   │   │   ├── server.py            # MCP server (separate process)
│   │   │   └── tools/
│   │   │       ├── github_tools.py  # get_pr_diff, post_comment, list_files
│   │   │       └── analysis_tools.py # semgrep_scan, ast_parse, complexity
│   │   ├── api/
│   │   │   ├── webhooks.py          # POST /webhook/github
│   │   │   ├── reviews.py           # GET /reviews, GET /reviews/{id}
│   │   │   └── stream.py            # GET /stream/{review_id} (SSE)
│   │   └── db/
│   │       ├── models.py            # SQLite models
│   │       └── crud.py              # CRUD operations
│   ├── tests/
│   │   ├── test_rate_limiter.py
│   │   ├── test_graph.py
│   │   └── test_mcp_tools.py
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx             # Main dashboard
│   │   │   ├── reviews/[id]/page.tsx # Review detail
│   │   │   └── layout.tsx
│   │   ├── components/
│   │   │   ├── PRList.tsx
│   │   │   ├── ReviewStream.tsx     # SSE reasoning trace streaming
│   │   │   ├── DiffViewer.tsx       # Annotated diff with findings
│   │   │   ├── FindingCard.tsx
│   │   │   ├── MetricsDashboard.tsx
│   │   │   └── RateLimitGauge.tsx   # Real-time quota usage display
│   │   └── lib/
│   │       ├── api.ts
│   │       └── types.ts
│   ├── package.json
│   └── .env.local.example
├── docker-compose.yml               # Backend + MCP server together
├── .github/workflows/ci.yml
└── README.md
```

### 3.2 End-to-end data flow

```
1.  GitHub sends webhook POST /webhook/github (event: PR opened/synchronize)
2.  FastAPI validates the HMAC-SHA256 webhook signature
3.  A Review record is created in the DB with status "pending"
4.  The LangGraph graph is launched as a background asyncio task
5.  The graph emits SSE events to the frontend as it progresses
6.  The Supervisor node reads the diff via MCP tool get_pr_diff
7.  The Supervisor decides which agents to activate and for which files
8.  The three worker agents run in parallel (asyncio.gather)
9.  Each agent calls its own MCP tools and queries the LLM
10. The Synthesis node aggregates findings, deduplicates, sorts by severity
11. [Optional HITL] The dashboard shows findings; the user approves
12. The Synthesis agent calls post_review_comment for each finding
13. The Review record is updated in the DB with status "completed"
```

---

## 4. LLM — Gemini 2.5 Flash

### 4.1 Configuration

```python
# backend/app/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    GEMINI_API_KEY: str
    GEMINI_MODEL: str = "gemini-2.5-flash"  # Configurable via .env

    # Rate limit config (Tier 1 values with 20% safety margin)
    RATE_LIMIT_RPM_MAX: int = 120       # 80% of 150 RPM Tier 1
    RATE_LIMIT_RPD_MAX: int = 1200      # 80% of 1500 RPD Tier 1
    RATE_LIMIT_TPM_MAX: int = 800_000   # 80% of 1M TPM Tier 1

    GITHUB_WEBHOOK_SECRET: str
    GITHUB_APP_ID: str
    GITHUB_PRIVATE_KEY_PATH: str

    LANGSMITH_API_KEY: str = ""
    LANGSMITH_TRACING: bool = False

    DATABASE_URL: str = "sqlite+aiosqlite:///./reviews.db"

    class Config:
        env_file = ".env"
```

### 4.2 LangChain integration

```python
from langchain_google_genai import ChatGoogleGenerativeAI
from app.rate_limiter import RateLimiter

def get_llm(rate_limiter: RateLimiter) -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=settings.GEMINI_MODEL,
        google_api_key=settings.GEMINI_API_KEY,
        temperature=0.1,        # Low temperature for deterministic analysis
        max_output_tokens=2048,
        callbacks=[rate_limiter.langchain_callback()],
    )
```

**Important note:** if `gemini-2.5-flash` is not available with your subscription, update `GEMINI_MODEL` in `.env` with the exact model name you have access to (e.g. `gemini-3-flash` if available as a preview). The architecture is completely model-agnostic.

---

## 5. Internal rate limiter (CRITICAL REQUIREMENT)

The rate limiter is the most important component for application stability. It must block calls **before** hitting the Google limit, not after receiving a 429.

### 5.1 Dimensions to monitor

| Dimension | Google Tier 1 limit | Internal threshold (80%) |
|---|---|---|
| RPM (requests/minute) | ~150 | **120** |
| RPD (requests/day) | ~1500 | **1200** |
| TPM (tokens/minute) | ~1,000,000 | **800,000** |

Exact Tier 1 values may vary — update `RATE_LIMIT_*` in `.env` if needed. The internal threshold is always calculated as 80% of the real limit.

### 5.2 Implementation specification

```python
# backend/app/rate_limiter.py
"""
Token bucket rate limiter across three independent dimensions.
Thread-safe via asyncio.Lock. RPD counter persisted in SQLite
to survive application restarts.
"""

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional
from app.config import settings

@dataclass
class RateLimiterState:
    # RPM: sliding window over the last 60 seconds
    rpm_window: deque = field(default_factory=deque)  # timestamps of last N requests

    # RPD: daily counter + reset timestamp
    rpd_count: int = 0
    rpd_reset_at: float = 0.0  # Unix timestamp of next Pacific midnight

    # TPM: sliding window of tokens over the last 60 seconds
    tpm_window: deque = field(default_factory=deque)  # (timestamp, tokens)

class RateLimiter:
    def __init__(self):
        self._state = RateLimiterState()
        self._lock = asyncio.Lock()

    async def acquire(self, estimated_tokens: int = 500) -> None:
        """
        Blocks until it is safe to make an API call.
        Raises DailyQuotaExhaustedError if the daily RPD quota is exhausted.
        """
        async with self._lock:
            now = time.time()
            self._refresh_windows(now)

            # Check RPD (daily limit — cannot recover by waiting)
            if self._state.rpd_count >= settings.RATE_LIMIT_RPD_MAX:
                reset_in = self._state.rpd_reset_at - now
                raise DailyQuotaExhaustedError(
                    f"Daily quota exhausted. Resets in {reset_in/3600:.1f} hours."
                )

            # Check RPM and TPM — wait if necessary
            await self._wait_for_rpm_capacity(now)
            await self._wait_for_tpm_capacity(now, estimated_tokens)

            # Record the request
            self._state.rpm_window.append(now)
            self._state.tpm_window.append((now, estimated_tokens))
            self._state.rpd_count += 1

    def _refresh_windows(self, now: float) -> None:
        """Remove entries older than 60 seconds from the sliding windows."""
        cutoff = now - 60
        while self._state.rpm_window and self._state.rpm_window[0] < cutoff:
            self._state.rpm_window.popleft()
        while self._state.tpm_window and self._state.tpm_window[0][0] < cutoff:
            self._state.tpm_window.popleft()

        # Reset RPD at Pacific midnight
        if now >= self._state.rpd_reset_at:
            self._state.rpd_count = 0
            self._state.rpd_reset_at = self._next_midnight_pacific()

    async def _wait_for_rpm_capacity(self, now: float) -> None:
        while len(self._state.rpm_window) >= settings.RATE_LIMIT_RPM_MAX:
            oldest = self._state.rpm_window[0]
            wait = (oldest + 60) - now + 0.1  # 100ms buffer
            await asyncio.sleep(max(0, wait))
            now = time.time()
            self._refresh_windows(now)

    async def _wait_for_tpm_capacity(self, now: float, tokens: int) -> None:
        current_tpm = sum(t for _, t in self._state.tpm_window)
        while current_tpm + tokens > settings.RATE_LIMIT_TPM_MAX:
            oldest_ts = self._state.tpm_window[0][0]
            wait = (oldest_ts + 60) - now + 0.1
            await asyncio.sleep(max(0, wait))
            now = time.time()
            self._refresh_windows(now)
            current_tpm = sum(t for _, t in self._state.tpm_window)

    def get_status(self) -> dict:
        """Returns the current rate limiter state for the frontend."""
        now = time.time()
        self._refresh_windows(now)
        return {
            "rpm_used": len(self._state.rpm_window),
            "rpm_max": settings.RATE_LIMIT_RPM_MAX,
            "rpd_used": self._state.rpd_count,
            "rpd_max": settings.RATE_LIMIT_RPD_MAX,
            "tpm_used": sum(t for _, t in self._state.tpm_window),
            "tpm_max": settings.RATE_LIMIT_TPM_MAX,
            "rpd_resets_at": self._state.rpd_reset_at,
        }

    @staticmethod
    def _next_midnight_pacific() -> float:
        """Returns the Unix timestamp of the next Pacific midnight (UTC-8)."""
        import datetime, zoneinfo
        tz = zoneinfo.ZoneInfo("America/Los_Angeles")
        now_pacific = datetime.datetime.now(tz)
        midnight = (now_pacific + datetime.timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return midnight.timestamp()


class DailyQuotaExhaustedError(Exception):
    pass
```

### 5.3 Monitoring endpoint

```
GET /api/rate-limit/status
```

Returns the current rate limiter state as JSON. The frontend polls this every 5 seconds to update the gauge.

### 5.4 Exponential backoff retry

For 429s that still arrive from Google (edge cases), implement retry with backoff:

```python
import tenacity

@tenacity.retry(
    wait=tenacity.wait_exponential(multiplier=1, min=4, max=60),
    stop=tenacity.stop_after_attempt(3),
    retry=tenacity.retry_if_exception_type(Exception),  # filter to 429 only
)
async def call_llm_with_retry(llm, messages):
    return await llm.ainvoke(messages)
```

---

## 6. MCP Server

### 6.1 Architecture

The MCP server is a separate Python process that exposes tools via stdio or HTTP. The FastAPI backend calls it as a local MCP client. In production, the MCP server runs as a Docker sidecar.

### 6.2 Exposed tools

#### GitHub tools

```
Tool: get_pr_diff
Input:  { repo: str, pr_number: int }
Output: { files: [{ filename, patch, additions, deletions, status }] }
Description: Fetches the full PR diff with per-file metadata.

Tool: list_pr_files
Input:  { repo: str, pr_number: int }
Output: { files: [{ filename, language, size_bytes }] }
Description: Lists modified files with metadata (used by the Supervisor).

Tool: post_review_comment
Input:  { repo: str, pr_number: int, body: str, commit_id: str,
          path: str, line: int, side: "LEFT"|"RIGHT" }
Output: { comment_id: int, url: str }
Description: Posts an inline comment on a specific diff line.

Tool: post_review_summary
Input:  { repo: str, pr_number: int, body: str,
          event: "COMMENT"|"APPROVE"|"REQUEST_CHANGES" }
Output: { review_id: int }
Description: Posts the overall review with a verdict.

Tool: get_pr_metadata
Input:  { repo: str, pr_number: int }
Output: { title, author, base_branch, head_branch, created_at, labels }
Description: Fetches PR metadata.
```

#### Analysis tools

```
Tool: semgrep_scan
Input:  { code: str, language: str, ruleset: "auto"|"security"|"owasp" }
Output: { findings: [{ rule_id, message, severity, line }] }
Description: Runs semgrep in a subprocess on a code chunk.

Tool: calculate_complexity
Input:  { code: str, language: str }
Output: { cyclomatic_complexity: float, cognitive_complexity: float,
          functions: [{ name, complexity, line }] }
Description: Uses radon for Python; regex-based fallback for JS/TS.

Tool: parse_ast
Input:  { code: str, language: str }
Output: { classes: [...], functions: [...], imports: [...], issues: [...] }
Description: tree-sitter for structural code analysis.

Tool: query_nvd_cve
Input:  { keyword: str, severity: "CRITICAL"|"HIGH"|"MEDIUM" }
Output: { cves: [{ id, description, cvss_score, published }] }
Description: Queries the National Vulnerability Database API.
```

### 6.3 GitHub App authentication

```python
# Use a JWT signed with the GitHub App private key.
# Do NOT use Personal Access Tokens (not scalable).
# Implement: app.get_installation_auth(installation_id)
# Every webhook payload includes the installation_id.
```

---

## 7. LangGraph graph

### 7.1 Shared state

```python
# backend/app/graph/state.py
from typing import TypedDict, Annotated, List, Optional
from langgraph.graph.message import add_messages

class PRFile(TypedDict):
    filename: str
    language: str
    patch: str
    additions: int
    deletions: int

class Finding(TypedDict):
    file: str
    line: int
    severity: str          # "critical" | "high" | "medium" | "low" | "info"
    category: str          # "security" | "quality" | "performance"
    rule_id: str
    message: str
    suggestion: str
    agent: str

class PRState(TypedDict):
    # Input
    repo: str
    pr_number: int
    commit_id: str

    # Extracted data
    files: List[PRFile]
    pr_metadata: dict

    # Agent assignment (decided by the Supervisor)
    security_files: List[str]
    quality_files: List[str]
    performance_files: List[str]

    # Agent outputs
    security_findings: List[Finding]
    quality_findings: List[Finding]
    performance_findings: List[Finding]

    # Final output
    all_findings: List[Finding]
    review_summary: str
    verdict: str           # "approve" | "comment" | "request_changes"

    # Streaming events (for SSE)
    events: Annotated[List[str], add_messages]

    # Human-in-the-loop
    hitl_approved: Optional[bool]
    hitl_modified_findings: Optional[List[Finding]]

    # Tracking
    review_id: str
    status: str
    error: Optional[str]
```

### 7.2 Graph nodes

#### Supervisor

```
Responsibilities:
- Calls list_pr_files and get_pr_diff via MCP
- Analyzes files and assigns each to the most appropriate agent
- Files with crypto imports, auth logic, SQL queries  → Security
- Files with high complexity, missing tests           → Quality
- Files with DB queries, nested loops, allocations   → Performance
- A single file can be assigned to multiple agents
- Emits SSE event: {"type": "supervisor_done", "files_count": N}
```

#### Security agent

```
Responsibilities:
- For each assigned file: calls semgrep_scan + query_nvd_cve
- Calls the LLM with the patch + tool results
- Produces Findings with severity critical/high/medium
- System prompt: application security expert, OWASP Top 10
- Emits SSE event: {"type": "security_done", "findings_count": N}
```

#### Quality agent

```
Responsibilities:
- For each file: calls calculate_complexity + parse_ast
- Checks: functions with complexity > 10, classes > 300 lines,
  missing tests, naming conventions, dead code
- Calls the LLM for contextual refactoring suggestions
- Emits SSE event: {"type": "quality_done", "findings_count": N}
```

#### Performance agent

```
Responsibilities:
- Static analysis for known patterns: N+1 queries (ORM),
  loops with I/O operations, string concatenation in loops,
  unused imports, allocations in hot paths
- Calls the LLM for contextual analysis
- Emits SSE event: {"type": "performance_done", "findings_count": N}
```

#### Synthesis agent

```
Responsibilities:
- Aggregates findings from all three agents
- Deduplication: removes identical findings (same line + same rule_id)
- Sorts by severity: critical → high → medium → low → info
- Generates a natural-language PR summary (max 300 words)
- Determines verdict: critical present → request_changes,
  only low/info → approve, otherwise → comment
- If HITL is enabled: pauses and waits for approval
- Otherwise: calls post_review_comment for each finding
  and post_review_summary with the summary
- Emits SSE event: {"type": "review_posted", "verdict": "..."}
```

### 7.3 Graph construction

```python
# backend/app/graph/graph.py
from langgraph.graph import StateGraph, END

def build_graph() -> StateGraph:
    graph = StateGraph(PRState)

    graph.add_node("supervisor", supervisor_node)
    graph.add_node("security", security_agent_node)
    graph.add_node("quality", quality_agent_node)
    graph.add_node("performance", performance_agent_node)
    graph.add_node("synthesis", synthesis_node)
    graph.add_node("hitl", hitl_node)  # Human-in-the-loop breakpoint

    graph.set_entry_point("supervisor")

    # Supervisor → 3 agents in parallel
    graph.add_edge("supervisor", "security")
    graph.add_edge("supervisor", "quality")
    graph.add_edge("supervisor", "performance")

    # Fan-in: all three agents must complete before synthesis
    graph.add_edge("security", "synthesis")
    graph.add_edge("quality", "synthesis")
    graph.add_edge("performance", "synthesis")

    # Conditional: HITL enabled or not
    graph.add_conditional_edges(
        "synthesis",
        lambda state: "hitl" if not state.get("hitl_approved") and HITL_ENABLED else END,
        {"hitl": "hitl", END: END}
    )

    graph.add_edge("hitl", END)

    return graph.compile(checkpointer=MemorySaver())
```

**Note:** LangGraph handles parallelization automatically when multiple nodes share the same source. Verify the exact fan-in syntax for the LangGraph version in use.

---

## 8. REST API — FastAPI

### 8.1 Endpoints

```
POST   /webhook/github              # Receive GitHub webhook
GET    /api/reviews                 # List reviews with pagination
GET    /api/reviews/{id}            # Review detail with findings
GET    /api/stream/{review_id}      # SSE stream of the reasoning trace
POST   /api/reviews/{id}/approve    # Approve findings (HITL)
PATCH  /api/reviews/{id}/findings   # Edit findings before posting (HITL)
GET    /api/rate-limit/status       # Rate limiter state
GET    /api/health                  # Health check
```

### 8.2 GitHub webhook handler

```python
# backend/app/api/webhooks.py

@router.post("/webhook/github")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    # 1. Validate HMAC-SHA256 signature
    signature = request.headers.get("X-Hub-Signature-256")
    body = await request.body()
    if not verify_signature(body, signature, settings.GITHUB_WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    event = request.headers.get("X-GitHub-Event")

    # Process only PR opened/synchronize events
    if event == "pull_request" and payload["action"] in ("opened", "synchronize"):
        review = await crud.create_review(payload)
        background_tasks.add_task(run_review_graph, review.id, payload)
        return {"review_id": review.id, "status": "queued"}

    return {"status": "ignored"}
```

### 8.3 SSE stream

```python
# backend/app/api/stream.py
from fastapi.responses import StreamingResponse

@router.get("/api/stream/{review_id}")
async def stream_review(review_id: str):
    async def event_generator():
        async for event in get_review_events(review_id):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )
```

---

## 9. Frontend — Next.js

### 9.1 Pages

**`/` — Main dashboard**
- List of analyzed PRs with status badge (pending / running / completed / failed)
- Aggregate metrics: total reviews, findings by category, weekly trend
- Rate limiter gauge (RPM / RPD / TPM) updated every 5s
- Link to each review

**`/reviews/[id]` — Review detail**
- PR header: title, repo, author, branch, verdict with color coding
- Left panel: reasoning trace in streaming (list of events with timestamps)
- Right panel: code diff annotated with inline findings per line
- Findings section: list filterable by category and severity
- HITL buttons: "Approve & post" / "Edit" / "Discard" (when HITL is enabled)

### 9.2 SSE streaming component

```typescript
// frontend/src/components/ReviewStream.tsx
"use client";
import { useEffect, useState } from "react";

type StreamEvent = {
  type: string;
  message: string;
  timestamp: string;
  data?: Record<string, unknown>;
};

export function ReviewStream({ reviewId }: { reviewId: string }) {
  const [events, setEvents] = useState<StreamEvent[]>([]);

  useEffect(() => {
    const sse = new EventSource(`/api/stream/${reviewId}`);

    sse.onmessage = (e) => {
      const event = JSON.parse(e.data) as StreamEvent;
      setEvents(prev => [...prev, event]);
    };

    sse.onerror = () => sse.close();
    return () => sse.close();
  }, [reviewId]);

  return (
    <div className="font-mono text-sm space-y-1">
      {events.map((e, i) => (
        <div key={i} className="flex gap-3">
          <span className="text-muted-foreground">{e.timestamp}</span>
          <span>{e.message}</span>
        </div>
      ))}
    </div>
  );
}
```

---

## 10. Database (SQLite)

### 10.1 Schema

```sql
-- Main reviews table
CREATE TABLE reviews (
    id TEXT PRIMARY KEY,              -- UUID
    repo TEXT NOT NULL,
    pr_number INTEGER NOT NULL,
    pr_title TEXT,
    pr_author TEXT,
    commit_id TEXT,
    status TEXT NOT NULL,             -- pending|running|completed|failed|hitl_pending
    verdict TEXT,                     -- approve|comment|request_changes
    summary TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME,
    error TEXT
);

-- Findings
CREATE TABLE findings (
    id TEXT PRIMARY KEY,
    review_id TEXT REFERENCES reviews(id),
    file TEXT NOT NULL,
    line INTEGER,
    severity TEXT NOT NULL,
    category TEXT NOT NULL,
    rule_id TEXT,
    message TEXT NOT NULL,
    suggestion TEXT,
    agent TEXT NOT NULL,
    posted_to_github BOOLEAN DEFAULT FALSE,
    github_comment_id TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- SSE events (for replay and persistence)
CREATE TABLE review_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id TEXT REFERENCES reviews(id),
    event_type TEXT NOT NULL,
    message TEXT,
    data TEXT,                        -- JSON
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Rate limiter counters (persist RPD across restarts)
CREATE TABLE rate_limit_state (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## 11. Security

### 11.1 Webhook authentication

- ALWAYS validate the HMAC-SHA256 signature (`X-Hub-Signature-256`) before processing any payload
- Compare using `hmac.compare_digest` (not `==`) to prevent timing attacks
- If the signature is missing or invalid: return 401 and log the attempt

### 11.2 Secrets management

- No secrets in source code or committed to the repository
- All secrets via environment variables (`.env` file, never committed)
- In production: use the secret managers provided by Railway/Render/Vercel
- `.env.example` must list ALL variable names with empty values

### 11.3 Required environment variables

```bash
# .env.example

# Gemini
GEMINI_API_KEY=your_google_api_key_here
GEMINI_MODEL=gemini-2.5-flash

# Rate limiter (update with your actual tier limits)
RATE_LIMIT_RPM_MAX=120
RATE_LIMIT_RPD_MAX=1200
RATE_LIMIT_TPM_MAX=800000

# GitHub App
GITHUB_APP_ID=your_app_id
GITHUB_PRIVATE_KEY_PATH=/app/secrets/github_private_key.pem
GITHUB_WEBHOOK_SECRET=your_webhook_secret

# LangSmith (optional)
LANGSMITH_API_KEY=
LANGSMITH_TRACING=false
LANGCHAIN_PROJECT=code-review-agent

# App
DATABASE_URL=sqlite+aiosqlite:///./reviews.db
HITL_ENABLED=false
CORS_ORIGINS=http://localhost:3000,https://your-frontend.vercel.app

# Frontend (Next.js)
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 11.4 CORS

- Allow only explicit origins (no `*` in production)
- Configurable list via the `CORS_ORIGINS` environment variable

### 11.5 Input sanitization

- The GitHub payload is trusted (authenticated via HMAC) but still validate with Pydantic
- Code extracted from the diff is NEVER executed directly
- semgrep is invoked on temporary files in an isolated directory

### 11.6 Rate limiter as an abuse defense

- The rate limiter also protects against internal abuse (review loops, duplicate webhooks)
- Implement webhook deduplication: ignore PRs with the same `commit_id` already under review

---

## 12. Testing

### 12.1 Priority unit tests

```
test_rate_limiter.py:
  - test_rpm_blocking: verify that the 121st request is blocked
  - test_rpm_release: verify that the window frees up after 60s
  - test_rpd_exhaustion: verify DailyQuotaExhaustedError is raised
  - test_tpm_blocking: verify blocking when token budget is exceeded
  - test_concurrent_requests: 20 parallel coroutines, none exceeds limits

test_graph.py:
  - test_supervisor_assigns_files: given a mock diff, verify agent assignment
  - test_parallel_agents: verify that the 3 agents run in parallel
  - test_synthesis_deduplication: identical findings are merged
  - test_verdict_logic: critical finding → request_changes

test_mcp_tools.py:
  - test_get_pr_diff_format: verify output structure
  - test_semgrep_scan: file with known vulnerability → expected finding
  - test_post_comment_payload: verify correct GitHub payload
```

### 12.2 Integration tests

- Use `pytest-asyncio` for all async code
- Mock `ChatGoogleGenerativeAI` with `unittest.mock` to avoid real API calls in tests
- GitHub fixtures with real webhook payloads (save examples in `tests/fixtures/`)

### 12.3 CI — GitHub Actions

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -e ".[dev]"
      - run: pytest tests/ -v --cov=app --cov-report=xml
      - run: semgrep --config auto backend/app/

  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20" }
      - run: cd frontend && npm ci && npm run build && npm run lint
```

---

## 13. Deployment

### 13.1 Backend — Railway or Render

```dockerfile
# backend/Dockerfile
FROM python:3.11-slim

WORKDIR /app
RUN apt-get update && apt-get install -y semgrep && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install -e .

COPY app/ ./app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```yaml
# docker-compose.yml (local development)
services:
  backend:
    build: ./backend
    ports: ["8000:8000"]
    env_file: ./backend/.env
    volumes: ["./backend/reviews.db:/app/reviews.db"]

  mcp-server:
    build: ./backend
    command: python -m app.mcp_server.server
    env_file: ./backend/.env
```

### 13.2 Frontend — Vercel

- Connect the GitHub repo to Vercel
- Set `NEXT_PUBLIC_API_URL` in Vercel environment variables
- Automatic deployment on every push to `main`

### 13.3 Local development setup

```bash
# Initial setup
git clone <repo>
cd autonomous-code-reviewer

# Backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env    # fill in your values
uvicorn app.main:app --reload

# Frontend (second terminal)
cd frontend
npm install
cp .env.local.example .env.local
npm run dev

# GitHub webhook tunnel (third terminal)
ngrok http 8000
# Update the Webhook URL in the GitHub App settings with the ngrok URL
```

---

## 14. Observability

### 14.1 LangSmith

With `LANGSMITH_TRACING=true`, every LangGraph run is traced automatically:
- Graph visualization with per-node timing
- Input/output of every LLM call
- Tokens used per call (useful for rate limiter debugging)
- Errors and retries

### 14.2 Application logging

```python
# Use structlog for structured JSON logging
import structlog
log = structlog.get_logger()

# Key events that must be logged:
log.info("review_started", review_id=review_id, repo=repo, pr_number=pr_number)
log.info("rate_limit_wait", dimension="rpm", wait_seconds=wait)
log.warning("daily_quota_low", rpd_used=used, rpd_max=max, pct=used/max*100)
log.error("review_failed", review_id=review_id, error=str(e))
```

### 14.3 Health check endpoint

```
GET /api/health
Response: {
  "status": "ok",
  "llm_model": "gemini-2.5-flash",
  "rate_limiter": { "rpm_used": 12, "rpm_max": 120, "rpd_used": 45, "rpd_max": 1200 },
  "db": "ok",
  "mcp_server": "ok"
}
```

---

## 15. Human-in-the-Loop (HITL)

When `HITL_ENABLED=true` (environment variable):

1. The graph pauses after the Synthesis node, before posting to GitHub
2. The review record transitions to `hitl_pending` status
3. The dashboard displays findings with "Approve" / "Edit" / "Discard" buttons
4. The user can edit the `message` and `suggestion` of each finding
5. Calling `POST /api/reviews/{id}/approve` resumes the graph
6. The graph continues from the breakpoint and posts to GitHub

LangGraph supports interrupt/resume natively via `interrupt_before=["hitl"]` in the compile call.

---

## 16. Portfolio considerations

### 16.1 What to highlight in the README

1. **LangGraph vs simple chains**: the graph explicitly models the flow, supports parallelism, HITL breakpoints, and error recovery — impossible with a linear chain
2. **Custom MCP server written from scratch**: not a wrapper — demonstrates understanding of the protocol
3. **Rate limiter as a first-class component**: not reactive 429 handling, but proactive prevention with sliding windows across three independent dimensions
4. **Streaming reasoning trace**: the user watches the agent "think" — a UX differentiator
5. **Separation of concerns**: each agent has a precise domain, the supervisor decides, synthesis aggregates — SOLID principles applied to agents

### 16.2 Demo script (10 minutes)

```
00:00 — Show the README and architecture diagram
02:00 — Open a PR with known vulnerabilities in a test repo
02:30 — Show the dashboard: review in "pending" status
03:00 — Watch the reasoning trace streaming live in the dashboard
05:00 — Review complete: show inline comments on GitHub
07:00 — Show LangSmith: graph with timing and token usage
08:30 — Show the rate limiter gauge: RPM/RPD in real time
09:30 — Open rate_limiter.py and explain the design choices
10:00 — Q&A
```

### 16.3 Test repository

Create a public GitHub repo `test-vulnerable-app` with intentionally problematic code:
- Obvious SQL injection (for the Security agent)
- Functions with cyclomatic complexity > 15 (for the Quality agent)
- Loops with DB queries inside (for the Performance agent)

---

## 17. Extension roadmap (post-MVP)

Features that can be added after the MVP to enrich the portfolio:

- **Multi-repo support**: handle webhooks from multiple GitHub organizations
- **Per-repo configuration**: `.codereview.yml` file in the target repo to customize rules and thresholds
- **Additional language support**: current priority is Python/JS/TS; add Go, Java
- **Historical PR score**: track code quality trends over time per repository
- **Slack/Teams notifications**: notify the team when a review is ready
- **Diff caching**: skip re-analyzing files unchanged between commits on the same PR
- **Batch review queue**: analyze multiple PRs with configurable priority

---

*End of document — REQUIREMENTS.md v1.0*
