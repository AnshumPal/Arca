"""
sandbox.py
Core sandbox agent logic for Arca Phase 4.

A sandbox is an isolated copy of a production agent running in shadow mode.
It receives the same inputs as production but NEVER responds to the user.
Its outputs are logged to sandbox_traces and evaluated by the same evaluator.

Design rules:
- Sandbox failure must NEVER affect the production response
- Sandbox runs as a background task — zero latency impact
- Config overrides supported: system_prompt, model, temperature
"""

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from openai import AsyncOpenAI
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import REGISTRY
from app.agents.base import get_client
from app.config import settings
from app.database import AsyncSessionLocal
from app.evaluator import evaluate_trace
from app.models import SandboxAgent, SandboxEvalScore, SandboxTrace

logger = logging.getLogger(__name__)

# Default system prompts per production agent — used when sandbox config
# does not override system_prompt
_AGENT_SYSTEM_PROMPTS: dict[str, str] = {
    "agent-1": (
        "You are Arca's intake agent. You handle general questions, "
        "clarify user intent, and provide clear, concise answers. "
        "If a request requires research or a specific action, say so clearly."
    ),
    "agent-2": (
        "You are Arca's research agent. You are given tasks that require "
        "gathering, analysing, and synthesising information. Provide structured, accurate, "
        "well-reasoned responses. Use bullet points or sections when the answer is complex."
    ),
    "agent-3": (
        "You are Arca's action agent. You execute specific tasks and "
        "return structured, actionable output. Be precise. If a task is ambiguous, "
        "ask one clarifying question before proceeding."
    ),
}

MIN_TRACES_FOR_VERDICT = 10


# ─── Trace adapter ─────────────────────────────────────────────────────────────
# evaluate_trace() expects a Trace ORM object. This adapter exposes the same
# attributes so the pure evaluator works unchanged with sandbox traces.

@dataclass
class _SandboxTraceAdapter:
    """Duck-typed adapter that lets evaluate_trace() score a SandboxTrace."""
    id: uuid.UUID
    latency_ms: Optional[int]
    input: str
    output: Optional[str]
    agent_id: str          # mapped from production_agent_id
    feedback: Optional[int]  # always None — sandboxes have no user feedback
    error: Optional[str]


# ─── Core sandbox functions ────────────────────────────────────────────────────

async def create_sandbox(
    name: str,
    production_agent_id: str,
    config: dict,
    db: AsyncSession,
) -> SandboxAgent:
    """
    Creates a new sandbox agent in the DB.
    Validates production_agent_id exists in REGISTRY.
    Raises ValueError if agent unknown or name already taken.
    """
    if production_agent_id not in REGISTRY:
        raise ValueError(f"Unknown production agent: {production_agent_id}")

    # Check for duplicate name
    existing = await db.execute(
        select(SandboxAgent).where(SandboxAgent.name == name)
    )
    if existing.scalar_one_or_none() is not None:
        raise NameError(f"Sandbox name already exists: {name}")

    sandbox = SandboxAgent(
        name=name,
        production_agent_id=production_agent_id,
        status="active",
        config=config,
    )
    db.add(sandbox)
    await db.commit()
    await db.refresh(sandbox)
    logger.info("Sandbox created: %s (%s) for %s", name, sandbox.id, production_agent_id)
    return sandbox


async def run_sandbox_shadow(
    sandbox: SandboxAgent,
    message: str,
    session_id: str,
    db: AsyncSession,
) -> Optional[SandboxTrace]:
    """
    Runs the sandbox agent on the same message as production (shadow mode).
    Never raises — errors are logged and written to the trace error field.
    Returns SandboxTrace or None on catastrophic failure.
    """
    cfg = sandbox.config or {}
    system_prompt = cfg.get("system_prompt") or _AGENT_SYSTEM_PROMPTS.get(
        sandbox.production_agent_id,
        "You are a helpful assistant.",
    )
    model = cfg.get("model") or settings.openai_model
    temperature = cfg.get("temperature")  # None = use API default

    output: Optional[str] = None
    error: Optional[str] = None
    prompt_used = f"[system]: {system_prompt}\n[user]: {message}"
    start = time.time()

    try:
        client: AsyncOpenAI = get_client()
        call_kwargs: dict = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": message},
            ],
        }
        if temperature is not None:
            call_kwargs["temperature"] = temperature

        try:
            completion = await client.chat.completions.create(**call_kwargs)
        except Exception as first_exc:
            # If the sandbox's configured model is deprecated / not available,
            # retry once with the current default model AND auto-suspend the
            # sandbox so it stops polluting logs. The trace records both facts.
            msg_lower = str(first_exc).lower()
            is_model_error = "model_not_found" in msg_lower or "does not exist" in msg_lower
            if is_model_error and model != settings.openai_model:
                logger.warning(
                    "Sandbox %s: model '%s' deprecated — retrying with default '%s' and suspending",
                    sandbox.id, model, settings.openai_model,
                )
                call_kwargs["model"] = settings.openai_model
                completion = await client.chat.completions.create(**call_kwargs)
                # Auto-suspend so subsequent shadow runs skip this sandbox
                sandbox.status = "suspended"
                error = f"[auto-suspended: model '{model}' deprecated, retried with {settings.openai_model}]"
            else:
                raise
        output = completion.choices[0].message.content or ""
    except Exception as exc:
        error = str(exc)
        logger.error("Sandbox %s LLM call failed: %s", sandbox.id, exc)

    latency_ms = int((time.time() - start) * 1000)

    # Write sandbox trace
    trace = SandboxTrace(
        sandbox_id=sandbox.id,
        production_agent_id=sandbox.production_agent_id,
        session_id=session_id or None,
        input=message,
        output=output,
        prompt_used=prompt_used,
        tools_used=[],
        latency_ms=latency_ms,
        error=error,
    )
    db.add(trace)
    await db.commit()
    await db.refresh(trace)

    # Evaluate using the production evaluator
    try:
        adapter = _SandboxTraceAdapter(
            id=trace.id,
            latency_ms=trace.latency_ms,
            input=trace.input,
            output=trace.output,
            agent_id=trace.production_agent_id,
            feedback=None,   # no user feedback for shadow runs
            error=trace.error,
        )
        eval_result = evaluate_trace(adapter)  # type: ignore[arg-type]

        for dim in eval_result.dimensions:
            score_row = SandboxEvalScore(
                sandbox_id=sandbox.id,
                sandbox_trace_id=trace.id,
                dimension=dim.dimension,
                score=dim.score,
                reasoning=dim.reasoning,
                overall_score=eval_result.overall_score,
            )
            db.add(score_row)
        await db.commit()
        logger.info(
            "Sandbox eval saved: sandbox=%s trace=%s overall=%.4f",
            sandbox.id, trace.id, eval_result.overall_score,
        )
    except Exception as exc:
        logger.error("Sandbox eval failed for trace %s: %s", trace.id, exc)

    return trace


async def get_active_sandboxes_for_agent(
    production_agent_id: str,
    db: AsyncSession,
) -> list[SandboxAgent]:
    """Returns all active sandboxes that copy the given production agent."""
    result = await db.execute(
        select(SandboxAgent).where(
            SandboxAgent.production_agent_id == production_agent_id,
            SandboxAgent.status == "active",
        )
    )
    return list(result.scalars().all())


async def get_sandbox_comparison(
    sandbox_id: str,
    db: AsyncSession,
) -> dict:
    """
    Compares sandbox eval scores vs production baseline for the same agent.
    Returns insufficient_data verdict if sandbox has fewer than MIN_TRACES_FOR_VERDICT traces.
    Delta = sandbox_score - production_score (positive = sandbox winning).
    """
    sid = uuid.UUID(sandbox_id) if isinstance(sandbox_id, str) else sandbox_id

    # Fetch sandbox
    result = await db.execute(select(SandboxAgent).where(SandboxAgent.id == sid))
    sandbox = result.scalar_one_or_none()
    if sandbox is None:
        raise ValueError(f"Sandbox not found: {sandbox_id}")

    # Count sandbox traces
    count_result = await db.execute(
        text("SELECT COUNT(*) FROM sandbox_traces WHERE sandbox_id = :sid"),
        {"sid": str(sid)},
    )
    sandbox_trace_count = count_result.scalar() or 0

    if sandbox_trace_count < MIN_TRACES_FOR_VERDICT:
        return {
            "sandbox_id": str(sid),
            "sandbox_name": sandbox.name,
            "production_agent_id": sandbox.production_agent_id,
            "verdict": "insufficient_data",
            "min_traces_required": MIN_TRACES_FOR_VERDICT,
            "sandbox_trace_count": sandbox_trace_count,
            "comparison": {},
        }

    # Sandbox dimension averages
    sb_stmt = text(
        """
        SELECT
            AVG(overall_score)                                          AS overall,
            AVG(CASE WHEN dimension = 'latency'  THEN score END)       AS latency,
            AVG(CASE WHEN dimension = 'length'   THEN score END)       AS length,
            AVG(CASE WHEN dimension = 'feedback' THEN score END)       AS feedback,
            AVG(CASE WHEN dimension = 'error'    THEN score END)       AS error
        FROM sandbox_eval_scores
        WHERE sandbox_id = :sid
        """
    )
    sb_result = await db.execute(sb_stmt, {"sid": str(sid)})
    sb_row = sb_result.fetchone()

    # Production baseline averages
    prod_stmt = text(
        """
        SELECT
            AVG(er.overall_score)                                           AS overall,
            AVG(CASE WHEN es.dimension = 'latency'  THEN es.score END)     AS latency,
            AVG(CASE WHEN es.dimension = 'length'   THEN es.score END)     AS length,
            AVG(CASE WHEN es.dimension = 'feedback' THEN es.score END)     AS feedback,
            AVG(CASE WHEN es.dimension = 'error'    THEN es.score END)     AS error
        FROM eval_runs er
        JOIN eval_scores es ON es.eval_run_id = er.id
        WHERE er.agent_id = :agent_id
        """
    )
    prod_result = await db.execute(prod_stmt, {"agent_id": sandbox.production_agent_id})
    prod_row = prod_result.fetchone()

    def _safe(row, col: str) -> float:
        val = getattr(row, col, None) if row else None
        return round(float(val), 4) if val is not None else 0.0

    comparison = {}
    for dim in ["overall", "latency", "length", "feedback", "error"]:
        sb_score   = _safe(sb_row,   dim)
        prod_score = _safe(prod_row, dim)
        comparison[dim] = {
            "production": prod_score,
            "sandbox":    sb_score,
            "delta":      round(sb_score - prod_score, 4),
        }

    overall_delta = comparison["overall"]["delta"]
    if abs(overall_delta) <= 0.02:
        verdict = "tied"
    elif overall_delta > 0:
        verdict = "sandbox_better"
    else:
        verdict = "production_better"

    return {
        "sandbox_id":          str(sid),
        "sandbox_name":        sandbox.name,
        "production_agent_id": sandbox.production_agent_id,
        "verdict":             verdict,
        "min_traces_required": MIN_TRACES_FOR_VERDICT,
        "sandbox_trace_count": sandbox_trace_count,
        "comparison":          comparison,
    }


async def suspend_sandbox(sandbox_id: str, db: AsyncSession) -> SandboxAgent:
    """Sets sandbox status to 'suspended'. Suspended sandboxes skip shadow execution."""
    sid = uuid.UUID(sandbox_id) if isinstance(sandbox_id, str) else sandbox_id
    result = await db.execute(select(SandboxAgent).where(SandboxAgent.id == sid))
    sandbox = result.scalar_one_or_none()
    if sandbox is None:
        raise ValueError(f"Sandbox not found: {sandbox_id}")
    sandbox.status = "suspended"
    await db.commit()
    await db.refresh(sandbox)
    return sandbox


async def delete_sandbox(sandbox_id: str, db: AsyncSession) -> SandboxAgent:
    """Soft-delete: sets status to 'deleted'. Data is retained for audit trail."""
    sid = uuid.UUID(sandbox_id) if isinstance(sandbox_id, str) else sandbox_id
    result = await db.execute(select(SandboxAgent).where(SandboxAgent.id == sid))
    sandbox = result.scalar_one_or_none()
    if sandbox is None:
        raise ValueError(f"Sandbox not found: {sandbox_id}")
    sandbox.status = "deleted"
    await db.commit()
    await db.refresh(sandbox)
    return sandbox


# ─── Background-safe wrapper ───────────────────────────────────────────────────

async def run_sandbox_shadow_bg(
    sandbox_id: str,
    message: str,
    session_id: str,
) -> None:
    """
    Background-safe wrapper — creates its own DB session.
    Never raises — all errors are logged.
    """
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(SandboxAgent).where(
                    SandboxAgent.id == uuid.UUID(sandbox_id),
                    SandboxAgent.status == "active",
                )
            )
            sandbox = result.scalar_one_or_none()
            if sandbox:
                await run_sandbox_shadow(sandbox, message, session_id, db)
    except Exception as exc:
        logger.error("Sandbox shadow bg error [%s]: %s", sandbox_id, exc)
