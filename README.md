# Arca

A controlled self-improving agent platform. Production agents handle real user requests, log every interaction as a structured trace, and a sandboxed copy of each agent can be tested with experimental changes — but nothing reaches production without passing an evaluation gate.

> *Arca* — Latin for vault or strongbox. Nothing gets out until it passes the gate.

---

## Setup (under 5 minutes)

### Prerequisites
- Docker + Docker Compose
- Python 3.11+ (for local dev / tests)
- An OpenAI API key

### 1. Clone and configure

```bash
git clone https://github.com/AnshumPal/Arca.git
cd Arca
cp .env.example .env
# Edit .env and set your OPENAI_API_KEY
```

### 2. Start the stack

```bash
docker compose up --build
```

- PostgreSQL starts on port `5432` with the `traces` table auto-created.
- FastAPI starts on port `8000`.
- Visit `http://localhost:8000/docs` for the interactive API explorer.

### 3. Run tests locally

```bash
pip install -r requirements.txt
# Make sure Postgres is running (docker compose up db)
pytest tests/ -v
```

---

## API Reference

### `POST /chat`
Send a message to the agent.

```json
// Request
{ "message": "What is the capital of France?", "session_id": "optional-session-id" }

// Response
{ "response": "Paris is the capital of France.", "trace_id": "uuid", "latency_ms": 843 }
```

### `POST /feedback`
Rate a response (1 = positive, -1 = negative).

```json
// Request
{ "trace_id": "uuid", "feedback": 1 }

// Response
{ "status": "ok" }
```

### `GET /traces`
List recent traces. Query params: `limit` (default 20, max 100), `session_id` (optional filter).

### `GET /report`
Aggregate summary across all traces.

```json
{
  "total_traces": 42,
  "avg_latency_ms": 761,
  "error_count": 2,
  "feedback": { "positive": 8, "negative": 1, "none": 33 },
  "generated_at": "2025-05-15T10:30:00Z"
}
```

---

## Architecture (Phase 1)

```
User → POST /chat
         ↓
    orchestrator.handle(message, session_id)
         ↓
    agent.run(message)   ← OpenAI API
         ↓ (response, prompt_used)
    tracer.write_trace(...)
         ↓ (trace_id)
    return ChatResponse(response, trace_id, latency_ms)
```

Every interaction is stored in the `traces` PostgreSQL table. The `/report` endpoint computes aggregates via SQL. No data leaves the local stack except OpenAI API calls.

---

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `OPENAI_API_KEY` | Your OpenAI API key | required |
| `OPENAI_MODEL` | Model to use | `gpt-4o-mini` |
| `DATABASE_URL` | SQLAlchemy async URL | `postgresql+asyncpg://arca:arca@localhost:5432/arca` |
| `POSTGRES_USER` | Postgres user | `arca` |
| `POSTGRES_PASSWORD` | Postgres password | `arca` |
| `POSTGRES_DB` | Postgres database name | `arca` |
| `APP_ENV` | Environment tag | `development` |
