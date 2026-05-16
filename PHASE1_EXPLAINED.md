# Arca — Phase 1 Explained (Plain English)

This document explains everything we built in Phase 1 in simple terms.
No jargon. Read this top to bottom and you'll understand the whole project.

---

## What is Arca in one sentence?

Arca is a system where an AI agent answers questions, and **every single
interaction is recorded** so the system can later measure, evaluate, and
improve the agent — in a controlled way.

Think of it like a black box flight recorder, but for AI conversations.

---

## The Big Picture — How it all connects

```
You (browser/curl)
       |
       | POST /chat  {"message": "What is Arca?"}
       ↓
  [FastAPI app — main.py]
       |
       ↓
  [Orchestrator — orchestrator.py]
    "OK, I'll pass this to the agent"
       |
       ↓
  [Agent — agent.py]
    "Let me call the LLM (Groq/OpenAI) and get a response"
       |
       ↓ response + prompt_used
  [Tracer — tracer.py]
    "Let me save everything to the database"
       |
       ↓
  [PostgreSQL database]
    traces table — one new row written
       |
       ↓ back to you
  {"response": "Arca is...", "trace_id": "uuid", "latency_ms": 843}
```

Every `/chat` request goes through all these steps in order.

---

## File by File — What each file does

### `app/main.py` — The front door
This is the FastAPI application. It defines the 4 API endpoints
(routes) that the outside world can call. Think of it as the
receptionist — it receives requests, passes them to the right
department, and sends back the response.

**4 endpoints it handles:**
- `POST /chat` — send a message, get a response
- `POST /feedback` — rate a response (👍 or 👎)
- `GET /traces` — see all recorded interactions
- `GET /report` — see summary stats

---

### `app/agent.py` — The brain
This is the AI agent. It takes a user message, builds a prompt,
calls the LLM (Groq or OpenAI), and returns the response.

It returns TWO things:
1. The response text (what the LLM said)
2. The exact prompt that was sent (stored for future analysis)

Why store the prompt? So in Phase 2/3, we can compare:
"When we used prompt A, quality was 60%. With prompt B, it's 80%."

```python
# The system prompt that shapes how the agent behaves
SYSTEM_PROMPT = """You are Arca, a reliable assistant.
Answer clearly and concisely. If you don't know something, say so."""
```

---

### `app/orchestrator.py` — The manager
A thin layer between the API endpoint and the agent.
Right now it just calls the agent directly, but in Phase 2+
it will decide WHICH agent to use, route to sandboxed agents,
run experiments, etc.

This is why we don't call agent.py directly from main.py —
the orchestrator is the extensibility point.

---

### `app/tracer.py` — The recorder
This file has 4 functions:

| Function | What it does |
|---|---|
| `write_trace()` | Saves one interaction to the database |
| `get_traces()` | Retrieves recent interactions |
| `update_feedback()` | Updates a trace with a thumbs up/down |
| `get_report()` | Runs SQL aggregates for the summary report |

Every time `/chat` is called — whether it succeeds or fails —
a row is written. Even errors are recorded. Nothing is lost.

---

### `app/models.py` — The database table shape
Defines what the `traces` table looks like using SQLAlchemy.
Each column maps to a piece of data we care about:

```
id            → unique ID for this interaction
session_id    → groups messages from the same user
agent_id      → which agent handled it (always "agent-1" in Phase 1)
input         → what the user said
output        → what the agent replied
prompt_used   → the full prompt sent to the LLM
latency_ms    → how long the LLM took to respond (in milliseconds)
error         → any error that occurred (null if success)
feedback      → 1 (thumbs up), -1 (thumbs down), null (no rating)
created_at    → timestamp
```

---

### `app/schemas.py` — The data contracts
Pydantic models that define the exact shape of requests and responses.
If someone sends wrong data (e.g. feedback = 5 instead of 1 or -1),
Pydantic rejects it automatically before it even reaches our code.

```python
# Example: feedback must be exactly 1 or -1, nothing else
class FeedbackRequest(BaseModel):
    trace_id: uuid.UUID
    feedback: Literal[1, -1]   # ← Pydantic enforces this
```

---

### `app/database.py` — The database connection
Sets up the async connection to PostgreSQL.
Creates the engine (the connection pool) and a session factory.
The `get_db()` function is a dependency injected into every endpoint
that needs database access.

---

### `db/init.sql` — The table blueprint
SQL that runs automatically when PostgreSQL starts for the first time.
It creates the `traces` table and two indexes:
- Index on `session_id` — fast lookup by session
- Index on `created_at DESC` — fast lookup of recent traces

---

### `docker-compose.yml` — The local environment
Defines two services that run together:

```
db  → PostgreSQL 15 database
       - Runs on port 5432
       - Mounts db/init.sql so table is auto-created on first start
       - Data persists in a named volume (postgres_data)

api → Your FastAPI app
       - Built from Dockerfile
       - Runs on port 8000
       - Waits for db to be healthy before starting
       - Reads config from .env file
```

Running `docker compose up --build` starts both together.

---

### `Dockerfile` — How to package the API
Instructions for building the API container:
1. Start from Python 3.11
2. Install all requirements
3. Copy the code
4. Run uvicorn (the web server)

---

### `tests/test_endpoints.py` — The automated tests
4 tests that verify the system works end to end:

| Test | What it checks |
|---|---|
| `test_chat_returns_response` | POST /chat returns 200 with response, trace_id, latency_ms |
| `test_chat_logs_trace` | After POST /chat, the trace appears in GET /traces |
| `test_feedback_updates_trace` | POST /feedback correctly updates the trace row |
| `test_report_structure` | GET /report has all required fields |

OpenAI/Groq is **mocked** in tests — no real API calls, no cost.
Tests use a real PostgreSQL database (same creds as dev).

---

### `.github/workflows/ci.yml` — Automatic testing on GitHub
Every time code is pushed to GitHub, this automatically:
1. Spins up a PostgreSQL database
2. Installs all Python packages
3. Runs all 4 tests
4. Builds the Docker image

If any step fails, the push is flagged with a red ❌.
If all pass, it shows a green ✅.

---

## The 4 API Endpoints — What they do

### POST /chat
**The main endpoint.** Send a message, get a response.

```
Request:  { "message": "What is Arca?", "session_id": "my-session" }
Response: { "response": "Arca is...", "trace_id": "uuid", "latency_ms": 843 }
```

Behind the scenes:
1. Starts a timer
2. Calls orchestrator → agent → LLM
3. Stops timer
4. Writes trace to DB (whether success or failure)
5. Returns response

---

### POST /feedback
**Rate a response.** You need the `trace_id` from a previous /chat call.

```
Request:  { "trace_id": "uuid", "feedback": 1 }
Response: { "status": "ok" }
```

`1` = thumbs up, `-1` = thumbs down.
Updates the `feedback` column on that trace row.

---

### GET /traces
**See all interactions.** Supports filtering by session.

```
GET /traces?limit=20&session_id=my-session
```

Returns a list of trace rows, newest first.

---

### GET /report
**Summary stats.** Everything computed with SQL aggregates (fast).

```json
{
  "total_traces": 42,
  "avg_latency_ms": 761.0,
  "error_count": 2,
  "feedback": {
    "positive": 8,
    "negative": 1,
    "none": 33
  },
  "generated_at": "2026-05-16T08:32:17Z"
}
```

This is the "nightly report" stub — in Phase 4+, this feeds into
the evaluation layer to decide if an agent should be promoted.

---

## What we deliberately did NOT build in Phase 1

The project brief was strict about this. These are for later phases:

| What | Why we skipped it |
|---|---|
| Sandbox agents | Phase 2 — copy of agent for safe experimentation |
| Eval / scoring layer | Phase 3 — scores agent responses automatically |
| Prompt optimizer | Phase 4 — rewrites prompts based on eval scores |
| Promotion gate | Phase 4 — controls what reaches production |
| Vector store / RAG | Phase 5 — gives agent access to documents |
| Frontend UI | Phase 6 — FastAPI /docs is enough for now |

---

## Environment Variables — Quick Reference

| Variable | What it's for |
|---|---|
| `OPENAI_API_KEY` | Your LLM API key (works for Groq too) |
| `OPENAI_MODEL` | Which model to use (e.g. `llama-3.1-8b-instant`) |
| `OPENAI_BASE_URL` | Switch providers — set to Groq URL to use Groq free tier |
| `DATABASE_URL` | How to connect to PostgreSQL |
| `POSTGRES_USER/PASSWORD/DB` | Postgres credentials (used by Docker) |
| `APP_ENV` | `development` or `test` |

---

## The Two .env Files

| File | Purpose | Committed to GitHub? |
|---|---|---|
| `.env` | **Real file** — has actual API keys, used by the app | ❌ No (in .gitignore) |
| `.env.example` | **Template** — placeholder values, shows teammates what's needed | ✅ Yes |

**Rule:** Never put real keys in `.env.example`. Anyone cloning the
repo copies `.env.example` → `.env` and fills in their own values.

---

## Phase 1 Definition of Done — Final Checklist

- [x] Folder structure + repo setup
- [x] PostgreSQL running via Docker (auto-creates traces table)
- [x] FastAPI app with 4 endpoints
- [x] Single agent using Groq/OpenAI SDK
- [x] Trace logging on every request (success AND failure)
- [x] GET /report with SQL aggregates
- [x] GitHub Actions CI
- [x] README with setup instructions
- [ ] CI green ✅ (verify at github.com/AnshumPal/Arca/actions)
- [ ] Real end-to-end smoke test (restart Docker → hit /chat → check /traces)

---

## What comes next — Phase 2 preview

Phase 1 gave us a working agent + reliable trace logging.
Phase 2 will add a **sandboxed copy** of the agent where we can
test changes safely, and an **eval layer** that scores responses
automatically by reading the traces we've been collecting.

The traces you're collecting right now in Phase 1 will become
the training signal for everything that follows.
