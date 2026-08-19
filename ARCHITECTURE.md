# Arca — Architecture & Design Document

> **A self-improving multi-agent AI platform where every response is scored,
> every experiment runs in isolation, and no change reaches production without
> passing a gate and explicit human approval.**

- **Live:** [arca-1.vercel.app](https://arca-1.vercel.app)
- **API:** [arca-pet9.onrender.com](https://arca-pet9.onrender.com)
- **Code:** [github.com/AnshumPal/Arca](https://github.com/AnshumPal/Arca)
- **Author:** Anshum Pal · B.Tech AI/ML @ RCOEM

---

## Table of contents

1. [What Arca is](#1-what-arca-is)
2. [Why it was built](#2-why-it-was-built)
3. [The core principle](#3-the-core-principle)
4. [How the loop works end-to-end](#4-how-the-loop-works-end-to-end)
5. [Phase-by-phase breakdown](#5-phase-by-phase-breakdown)
6. [Stack & infrastructure](#6-stack--infrastructure)
7. [Real-world metrics](#7-real-world-metrics)
8. [What Arca is NOT](#8-what-arca-is-not)
9. [Interview talking points](#9-interview-talking-points)
10. [What comes next](#10-what-comes-next)

---

## 1. What Arca is

Arca is a **production-grade multi-agent platform** with three specialised
agents (intake, research, action) that serve live user requests. Every
interaction is logged as a structured trace and automatically scored across
four evaluation dimensions.

Beyond that, Arca is a **closed self-improvement loop**:
- Sandbox agents shadow live traffic to test experimental changes safely
- A nightly optimizer detects failure patterns and proposes improved prompts
- A promotion gate enforces four checks before any change reaches production
- A human still has the final approval before anything goes live
- Rollback is one command away

The name **Arca** — Latin for *vault* — reflects the core promise:
**nothing leaves the vault without passing the gate.**

---

## 2. Why it was built

Most "AI agent" projects fall into one of two failure modes:

1. **Chatbot wrappers** — call an LLM, return the response, end of story.
   No observability, no metrics, no way to improve.
2. **Unsafe self-optimisers** — autonomous loops that modify themselves
   with no gate. When something breaks, no one knows why.

Arca was built to demonstrate a middle path:

> *An agent system that improves itself, but under controlled, measurable,
> and reversible conditions.*

This directly answers the interview question every senior engineer asks:

> *"How do you make sure the AI doesn't break things while trying to improve
> itself?"*

---

## 3. The core principle

Two rules govern every design decision in Arca:

> **Observe before you optimize.**
> **Gate before you promote.**

Concretely:
- You cannot safely improve what you have not measured.
- You cannot safely promote what you have not tested in isolation.
- You should not deploy what no human has approved.

Every phase enforces one of these principles.

---

## 4. How the loop works end-to-end

```
    ┌─────────────────────────────────────────────────────────────┐
    │                        USER REQUEST                          │
    └──────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │   Keyword Router     │  → picks 1 of 3 agents
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │  Production Agent    │  → responds to user
                    └──────────┬───────────┘
                               │
                    ┌──────────┴──────────┐
                    ▼                     ▼
          ┌─────────────────┐   ┌──────────────────┐
          │  Trace logged   │   │ Shadow sandboxes │  → same input,
          │   to Postgres   │   │  run in parallel │    never respond
          └────────┬────────┘   └────────┬─────────┘
                   │                     │
                   ▼                     ▼
          ┌─────────────────┐   ┌──────────────────┐
          │  Auto-evaluate  │   │  Sandbox scored  │
          │  4 dimensions   │   │   independently  │
          └────────┬────────┘   └────────┬─────────┘
                   │                     │
                   └──────────┬──────────┘
                              │
                              ▼
                   ┌────────────────────┐
                   │  Nightly optimizer │  (02:00 UTC)
                   │  reads 7 days of   │  → detects failure patterns
                   │    eval scores     │  → LLM proposes new prompts
                   └──────────┬─────────┘  → spins up sandbox candidates
                              │
                              ▼
                   ┌────────────────────┐
                   │  Promotion gate    │  → 4 automated checks
                   │  (advisory)        │
                   └──────────┬─────────┘
                              │
                              ▼
                   ┌────────────────────┐
                   │   Human approval   │  → the only path to production
                   └──────────┬─────────┘
                              │
                              ▼
                   ┌────────────────────┐
                   │ Live within 30 sec │  → cached prompt hot-reload
                   │ Rollback available │
                   └────────────────────┘
```

---

## 5. Phase-by-phase breakdown

Arca was built across **six phases**, each answering one specific question.
This section explains what each phase does, why it exists, and how it works.

### Phase 1 — Foundation: single agent with tracing

**Question:** Can we log every LLM interaction as structured data?

**What was built:**
- FastAPI app with `POST /chat` and `POST /feedback`
- PostgreSQL `traces` table capturing input, output, prompt used, latency,
  errors, feedback signal, session ID, timestamp
- Docker + docker-compose for local dev
- GitHub Actions CI on every push

**Why it matters:** Without traces, nothing else in Arca is possible. This
is the foundational observability layer.

**Key files:** `app/main.py`, `app/tracer.py`, `app/models.py`

---

### Phase 2 — Multi-agent routing

**Question:** Can we specialise agents by intent while keeping a single API?

**What was built:**
- Three agents in `app/agents/` — `intake` (Agent-1), `research` (Agent-2),
  `action` (Agent-3), each with its own system prompt
- Keyword classifier in `app/router.py` that inspects the user message
  and dispatches to the right agent
- `REGISTRY` dict mapping `agent_id` → `run()` + description
- `GET /agents` and `GET /health` endpoints

**Why it matters:** Real production agent systems delegate to specialists.
This models that architecture with the simplest possible router — no
external dependency, understandable in 30 seconds.

**Key files:** `app/agents/{intake,research,action}.py`, `app/router.py`,
`app/orchestrator.py`

**Known limitation:** the router is keyword-based. It misses semantic intent
(e.g. "how are you made" routes to intake instead of research). A future
phase could replace it with a lightweight LLM classifier.

---

### Phase 3 — The evaluation engine

**Question:** How do we measure whether an agent is doing well?

**What was built:**
- `app/evaluator.py` — pure scoring functions, no DB calls, no external APIs
- Four dimensions with weighted average (feedback carries the most weight):

  | Dimension | Weight | What it measures |
  |-----------|--------|------------------|
  | latency   | 0.20   | How fast the agent responded |
  | length    | 0.25   | Whether output length fits the agent's ideal range |
  | feedback  | 0.35   | 👍 = 1.0 · no signal = 0.5 · 👎 = 0.0 |
  | error     | 0.20   | 1.0 = clean · 0.5 = empty · 0.0 = crashed |

- `eval_runs` and `eval_scores` tables
- `app/eval_runner.py` — DB read/write for eval results
- **Every `POST /chat` triggers a background evaluation via FastAPI
  BackgroundTasks — zero latency added to user response**
- Four new endpoints:
  - `GET /eval/scores` — dimension scores per trace
  - `GET /eval/report` — per-agent averages (SQL aggregates)
  - `GET /eval/compare?agent_a=X&agent_b=Y` — head-to-head comparison
  - `POST /eval/run` — manually trigger evaluation

**Why it matters:** You cannot improve what you do not measure. Everything
after Phase 3 depends on real scores.

**Design note:** the evaluator makes **zero LLM calls**. Scores are
deterministic from trace data. Fast, free, reproducible.

**Key files:** `app/evaluator.py`, `app/eval_runner.py`, `app/eval_schemas.py`

---

### Phase 4 — Sandbox shadow execution

**Question:** How do we test experimental agent variants without risking
production?

**What was built:**
- `sandbox_agents` table: each row is an experimental agent copy with
  a config diff (system_prompt, model, temperature overrides)
- `sandbox_traces` and `sandbox_eval_scores` — **separate tables** from
  production, no cross-contamination possible
- `app/sandbox.py` — create, run in shadow, suspend, delete, compare
- **Shadow execution:** every `POST /chat` also runs every active sandbox
  in the background. Sandboxes see the same inputs but **never respond
  to the user**
- Sandbox traces are scored by the exact same `evaluator.py` — same yardstick
- Five endpoints:
  - `POST /sandbox` — create with config overrides
  - `GET /sandbox` — list with filters (status, production_agent_id)
  - `GET /sandbox/{id}` — full detail + per-dimension averages
  - `GET /sandbox/{id}/compare` — sandbox vs production baseline
  - `DELETE /sandbox/{id}?action=suspend|delete`

**Why it matters:** This is the safety layer. You can propose 100
experimental prompt variants and none of them ever touch a real user
until they prove themselves.

**Design rules enforced:**
- Sandbox failure never affects the production response
- Sandbox runs are always background tasks — zero latency impact
- Compare returns `insufficient_data` verdict below 10 traces to avoid
  noisy small-sample comparisons

**Key files:** `app/sandbox.py`, `app/sandbox_schemas.py`

---

### Phase 5 — The autoresearch optimizer

**Question:** Can the system detect its own weaknesses and propose fixes?

**What was built:**

**`app/analyzer.py`** — pure analysis, no LLM calls:
- Reads eval scores per agent over the last 7 days
- Compares each dimension avg to failure thresholds:
  - latency < 0.60 → flagged
  - length < 0.65 → flagged
  - feedback < 0.55 → flagged
  - error < 0.85 → flagged (safety-critical, higher bar)
- For each flagged dimension, pulls the **5 worst-performing real inputs**
  (grounded in actual user queries, not synthetic examples)
- Returns structured `FailurePattern` objects

**`app/proposer.py`** — the ONE place in Phase 5 that calls an LLM:
- Sends the current system prompt + failure pattern + 5 worst inputs
  to OpenAI/Groq
- Asks for a `{proposed_prompt, reasoning}` JSON response
- One LLM call per failure pattern per optimizer cycle

**`app/optimizer.py`** — the orchestrator:
- Creates an `optimizer_runs` row with `status='running'`
- Calls `analyze_all_agents()` → gets failure patterns
- For each pattern → calls `propose_improvement()` → creates sandbox
- Skips duplicate sandbox names (idempotent within a cycle)
- Marks run `completed` or `failed` — **never leaves a run stuck at 'running'**

**`app/scheduler.py`** — APScheduler nightly job at 02:00 UTC.

**Four endpoints:**
- `POST /optimizer/run` — manual trigger (synchronous, returns when done)
- `GET /optimizer/runs` — list all past runs
- `GET /optimizer/runs/{id}` — full detail including findings & proposals
- `GET /optimizer/schedule` — next scheduled run + last run status

**Why it matters:** This is the "self-improving" part. The system finds
its own weakest link every night and proposes a fix — with zero human
involvement in the analysis or proposal loop.

**Key files:** `app/analyzer.py`, `app/proposer.py`, `app/optimizer.py`,
`app/scheduler.py`

---

### Phase 6 — Promotion gate + rollback

**Question:** How do we let the system improve itself without letting bad
changes reach production?

**What was built:**

**Four automated gate checks** (`app/gate.py`):

| Check | Threshold | Purpose |
|-------|-----------|---------|
| `min_traces`             | ≥ 10   | Statistical significance |
| `min_overall_delta`      | ≥ 0.05 | Sandbox must be *meaningfully* better |
| `min_error_score`        | ≥ 0.80 | Safety floor — no promotion if error rate spikes |
| `max_latency_regression` | ≥ -0.10 | Allow slight slowdown, not catastrophic |

**Gate design philosophy:** the gate is **advisory, not blocking**.
It runs on every promotion request, but a failing gate does not block
the pending record from being created. The human sees exactly which
checks failed and decides. Reason: sometimes you promote anyway (e.g.
early in the project when data is thin).

**`app/version_manager.py`** — full version history per agent:
- Every agent starts at v1 (original hardcoded prompt, recorded on first
  promotion request)
- Each promotion creates v2, v3, ... marks the new one `is_current=True`,
  unsets all others
- Rollback flips `is_current` back to any previous version — no destruction

**`app/promoter.py`** — the state machine:
- `request_promotion()` — runs gate, creates pending record
- `approve_promotion()` — creates new version, suspends sandbox, invalidates
  prompt cache
- `reject_promotion(reason)` — sandbox stays active for more data
- `execute_rollback(to_version, reason)` — one-command restore

**Dynamic prompt loading** (`app/agents/base.py`):
- `get_live_prompt(agent_id, hardcoded_fallback)` checks `agent_versions`
  table for the current version
- Falls back to hardcoded prompt if no version exists
- **30-second in-memory TTL cache** — new promotions go live within 30
  seconds without a server restart or redeploy
- Cache invalidated immediately on approval or rollback

**Seven new endpoints:**
- `POST /promote/{sandbox_id}` — runs gate, creates pending record
- `GET /promote` — list with filters (status, agent_id)
- `GET /promote/{id}` — full gate check breakdown
- `POST /promote/{id}/approve` — human approves
- `POST /promote/{id}/reject` — human rejects with reason
- `GET /agents/{id}/versions` — full version history
- `POST /agents/{id}/rollback` — restore any previous version
- `GET /rollbacks` — audit log of every rollback

**Why it matters:** This is what makes Arca safe. No matter how confidently
the optimizer proposes changes, none of them reach real users without
passing 4 checks AND explicit human approval. And if something degrades
in production, rollback is one API call away — 30 seconds to restore.

**Key files:** `app/gate.py`, `app/version_manager.py`, `app/promoter.py`,
`app/promotion_schemas.py`

---

### Phase 7 — Frontend dashboard

**Question:** How do we make all of this visible and demoable?

**What was built:** a Next.js 14 dashboard at `arca-1.vercel.app` with
7 pages:

| Page | What it shows |
|------|---------------|
| `/`           | Editorial landing — hero + 3 agent showcase cards + method section |
| `/chat`       | Live chat with feedback rating (👍 / 👎) per response |
| `/dashboard`  | Per-agent scorecards with 4-dimension bar charts |
| `/sandboxes`  | List of active/suspended/deleted sandboxes |
| `/sandboxes/[id]` | Config diff, per-dim averages, sandbox-vs-production compare table |
| `/optimizer`  | Recent runs + expandable findings/proposals + manual trigger |
| `/promotions` | Approval queue with per-check gate breakdown + approve/reject |
| `/versions`   | Per-agent timeline of every prompt version + rollback button |

**Stack:**
- Next.js 14 App Router + TypeScript + Tailwind CSS
- Fraunces serif (display) + Inter (body) via `next/font/google`
- Typed API client wrapping all 25 backend endpoints
- Editorial copper/cream dark theme

**Why it matters:** Swagger docs are for developers. This dashboard is
for humans — including recruiters and interviewers.

---

## 6. Stack & infrastructure

### Backend
- **FastAPI** — async web framework
- **SQLAlchemy 2.0 async + asyncpg** — DB layer
- **PostgreSQL** — trace storage, 10 tables across 5 migrations
- **Pydantic v2** — request/response validation
- **APScheduler** — nightly optimizer cron
- **OpenAI SDK** — with base_url override for Groq compatibility
- **pytest + pytest-asyncio** — 37 passing tests

### Frontend
- **Next.js 14** (App Router) + TypeScript
- **Tailwind CSS** — styling
- **Fraunces + Inter** — typography

### Infrastructure ($0/month)
- **Render** — backend hosting (free tier, UptimeRobot ping to prevent sleep)
- **Neon** — PostgreSQL (free tier, serverless Postgres)
- **Vercel** — frontend hosting (free tier)
- **Groq** — LLM inference (free tier, llama-3.3-70b-versatile)
- **GitHub Actions** — CI/CD, deploys on every push to main

### Data model (10 tables)

```
traces                  ← every user chat
eval_runs               ← one per evaluated trace
eval_scores             ← 4 rows per eval_run (one per dimension)
sandbox_agents          ← experimental agent copies
sandbox_traces          ← shadow-mode outputs (never seen by users)
sandbox_eval_scores     ← per-dimension scores for sandbox traces
optimizer_runs          ← one per nightly cycle
agent_versions          ← every prompt version ever shipped
promotions              ← every promotion attempt + gate results
rollbacks               ← audit log
```

---

## 7. Real-world metrics

Numbers pulled directly from `/eval/report` — screenshotable, defensible.

### Traffic (2 months)
- **320 live production chats** across 3 agents
  - agent-1 (intake): 228 chats
  - agent-2 (research): 28 chats
  - agent-3 (action): 64 chats
- **80 automated evaluations recorded**
- **20+ unique user sessions**
- **100% completion rate** (zero errors, zero empty outputs)

### Quality
- **Weighted overall score: 0.73**
- **Best agent: agent-3 (Action) at 0.7844**
- **Length calibration: perfect (1.00) for agent-2 and agent-3**
- **Latency: 143ms best-case (warm), 4.5s typical for research agent**

### What the eval loop caught
| Issue | How caught | Fix |
|-------|-----------|-----|
| agent-2 latency 0.54 < 0.60 threshold | analyzer.py flagged as failure pattern | prompt tightened to 150-350 word target |
| Model confabulating "Arca" as musician / crypto | manual trace review after eval scores looked fine | upgraded llama-3.1-8b → llama-3.3-70b |
| Only 1.5% user feedback engagement | analyzer.py flagged feedback dim stuck at 0.50 | frontend redesign to make 👍/👎 more prominent (pending) |

**Key insight:** the eval framework surfaced problems that unit tests
never could — because they were **behavioural**, not correctness bugs.

---

## 8. What Arca is NOT

Being honest about scope matters. Arca is **not**:

- ❌ A production customer-facing product — it's a research demo
- ❌ A LangChain / LangGraph replacement — router logic is a keyword
  classifier, deliberately kept simple
- ❌ A RAG system — no vector store, no document retrieval
- ❌ Optimising with real reinforcement learning — the "optimizer" is
  a rule-based analyser + LLM prompt suggestion loop
- ❌ Fully autonomous — a human is always in the promotion loop by design

Understanding the boundary is as important as understanding the capability.

---

## 9. Interview talking points

### "Walk me through Arca."

> *"Arca is a self-improving agent platform built around one principle:
> observe before you optimize, gate before you promote.*
>
> *Three production agents handle live requests — intake, research, action.
> Every interaction is logged as a trace. A background evaluator scores
> it on four dimensions. Those scores accumulate into per-agent scorecards.*
>
> *Every night the optimizer runs. It finds dimensions where an agent is
> underperforming, pulls the five worst real inputs, and calls OpenAI once
> per pattern to propose a better prompt. That prompt goes into a sandbox
> that runs in shadow mode — same inputs, never responds to users.*
>
> *After 10 shadow traces the compare endpoint shows whether it's better.
> If it is, I can request promotion. The gate runs four checks. If it
> passes, a pending record is created. I review the gate results and
> approve. Within 30 seconds the production agent is on the new prompt.
> If it degrades, one rollback command restores the previous version.*
>
> *That's the vault. Nothing leaves without passing the gate."*

### "How is Arca different from a chatbot wrapper?"

> *"Most agent projects just call an LLM and return the response. Arca
> evaluates every response across four dimensions and stores those scores
> so the system knows which agent is performing better before it tries
> to improve anything. You can't safely optimize what you haven't measured."*

### "How do you test changes safely?"

> *"Every production agent has a sandbox counterpart. When I want to
> test a new system prompt or model, I create a sandbox with that config.
> It runs in shadow mode — sees every live message, never responds to
> the user. After 10+ traces I have real evaluation scores to compare
> against production. Nothing gets promoted until the sandbox is provably
> better AND a human approves."*

### "What has the platform taught you?"

> *"After 320 live chats, my own eval engine flagged three things I
> hadn't caught in testing:*
>
> *1. My research agent's latency scored 0.54 — below my 0.60 threshold —
> because I never capped its output length.*
>
> *2. My small model was confidently hallucinating that 'Arca' is a
> musician because the name collides with a real one. Eval scores stayed
> healthy while responses were factually wrong. Taught me evaluation
> dimensions have blind spots.*
>
> *3. Only 1.5% of users gave explicit feedback, so my feedback dimension
> was mostly noise. I'm now working on implicit signals — session length,
> follow-up rate.*
>
> *Every one of those insights came from the observability layer. That's
> why I built it before the optimizer."*

---

## 10. What comes next

Phases 1–7 are shipped and live. Real candidates for future work:

- **Phase 8 — Semantic router.** Replace keyword classifier with a
  lightweight LLM classifier for better intent detection.
- **Implicit feedback signals.** Track session length, follow-up rate,
  copy-to-clipboard actions to supplement thin 👍/👎 data.
- **Multi-model routing.** Automatically route simple queries to a
  cheaper/faster model, complex ones to a larger one.
- **A/B traffic splitting.** Instead of shadow mode only, route a small
  % of real traffic to a sandbox to get real user feedback.
- **Cost telemetry.** Track $ spent per query per agent so the optimizer
  can factor cost into its proposals.

None of these are needed for the current story. They're candidates when
Arca graduates from portfolio project to production system.

---

## Credits

Built by [Anshum Pal](https://github.com/AnshumPal) as a portfolio project
demonstrating end-to-end systems design for AI infrastructure roles.

License: MIT.
