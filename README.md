# GitMind — Autonomous Code Review Agent
<div>

**AI-powered code review agent that analyzes GitHub Pull Requests for security vulnerabilities, code quality issues, and performance bottlenecks in real-time.**

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![Next.js 14](https://img.shields.io/badge/Next.js-14-000000?logo=nextdotjs)](https://nextjs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-1C3C3C)](https://langchain-ai.github.io/langgraph/)
[![Gemini](https://img.shields.io/badge/Gemini_2.5_Flash-4285F4?logo=google)](https://ai.google.dev)

</div>

---

## 🏗️ Architecture

```
GitHub PR → Webhook → FastAPI → LangGraph Pipeline → Gemini 2.5 Flash → GitHub Comments
                                    │
                          ┌─────────┼─────────┐
                          ▼         ▼         ▼
                       Security  Quality  Performance
                        Agent     Agent      Agent
                          └─────────┼─────────┘
                                    ▼
                              Synthesis Node
                                    │
                          ┌─────────┼─────────┐
                          ▼         ▼         ▼
                    Dedup + Sort  Verdict   Post to GH
```

### Key Technical Highlights

1. **LangGraph multi-agent pipeline** — Supervisor dispatches to 3 parallel specialist agents with fan-out/fan-in topology
2. **Custom MCP server** — Written from scratch (not a library wrapper) with 8 tools for GitHub and static analysis
3. **Proactive rate limiter** — Blocks calls *before* hitting Google limits using sliding windows across 3 independent dimensions (RPM/RPD/TPM)
4. **Real-time SSE streaming** — Watch the agent "think" with live reasoning trace in the dashboard
5. **Human-in-the-Loop** — Optional approval step before posting findings to GitHub

---

## 🚀 Quick Start

```bash
# Clone and run
git clone <repo-url>
cd GitMind

# One-command start (Windows)
start.bat
```

See [GUIDE.md](GUIDE.md) for detailed setup instructions including API keys and test repository creation.

---

## 📁 Project Structure

```
GitMind/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entrypoint
│   │   ├── config.py            # Pydantic settings
│   │   ├── rate_limiter.py      # Three-dimension rate limiter
│   │   ├── api/                 # REST endpoints (webhook, reviews, SSE)
│   │   ├── db/                  # SQLite models & CRUD
│   │   ├── graph/               # LangGraph pipeline
│   │   │   ├── supervisor.py    # File triage & agent assignment
│   │   │   ├── agents/          # Security, Quality, Performance agents
│   │   │   ├── synthesis.py     # Aggregation & verdict
│   │   │   └── graph.py         # Graph construction
│   │   └── mcp_server/          # Custom MCP server with 8 tools
│   └── tests/
├── frontend/                    # Next.js 14 dashboard
│   └── src/
│       ├── app/                 # Pages (dashboard, review detail)
│       ├── components/          # UI components (SSE stream, diff viewer, etc.)
│       └── lib/                 # API client & types
├── GUIDE.md                     # Testing guide
├── start.bat                    # One-click launch script
└── docker-compose.yml
```

---

## ⚙️ Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.11+, FastAPI, LangGraph, LangChain |
| **LLM** | Gemini 2.5 Flash via langchain-google-genai |
| **MCP Server** | Python MCP SDK (custom, stdio transport) |
| **Database** | SQLite via aiosqlite |
| **Frontend** | Next.js 14, TypeScript, Tailwind CSS |
| **Streaming** | Server-Sent Events (SSE) |
| **GitHub** | PyGithub + GitHub App authentication |
| **Analysis** | radon (complexity), AST parsing, semgrep (optional) |

---

## 📊 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/webhook/github` | GitHub webhook receiver |
| `GET` | `/api/reviews` | List reviews (paginated) |
| `GET` | `/api/reviews/{id}` | Review detail with findings |
| `GET` | `/api/stream/{id}` | SSE reasoning trace |
| `POST` | `/api/reviews/trigger` | Manual review trigger |
| `POST` | `/api/reviews/{id}/approve` | HITL approval |
| `GET` | `/api/rate-limit/status` | Rate limiter state |
| `GET` | `/api/health` | Health check |

---



## 📄 License

MIT
