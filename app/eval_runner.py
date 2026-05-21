"""
eval_runner.py
Orchestrates running evaluations: single trace, batch, or all unevaluated.
Writes results to eval_runs and eval_scores tables.
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.evaluator import evaluate_trace
from app.models import EvalRun, EvalScore, Trace

logger = logging.getLogger(__name__)


async def run_eval_for_trace(trace_id: str, db: AsyncSession) -> EvalRun:
    """
    1. Fetch trace by trace_id
    2. Call evaluator.evaluate_trace(trace)
    3. Upsert into eval_runs (update if already exists)
    4. Delete old eval_scores for this run, insert new ones
    5. Return the EvalRun ORM object
    """
    tid = uuid.UUID(trace_id) if isinstance(trace_id, str) else trace_id

    # Fetch trace
    result = await db.execute(select(Trace).where(Trace.id == tid))
    trace = result.scalar_one_or_none()
    if trace is None:
        raise ValueError(f"Trace not found: {trace_id}")

    # Score it
    eval_result = evaluate_trace(trace)

    # Upsert eval_run (update if trace already evaluated)
    existing = await db.execute(select(EvalRun).where(EvalRun.trace_id == tid))
    eval_run = existing.scalar_one_or_none()

    if eval_run is None:
        eval_run = EvalRun(
            trace_id=tid,
            agent_id=eval_result.agent_id,
            overall_score=eval_result.overall_score,
            evaluated_at=datetime.now(timezone.utc),
            eval_version=eval_result.eval_version,
        )
        db.add(eval_run)
        await db.flush()  # get eval_run.id without committing
    else:
        eval_run.overall_score = eval_result.overall_score
        eval_run.evaluated_at = datetime.now(timezone.utc)
        eval_run.eval_version = eval_result.eval_version
        # Delete old dimension scores before re-inserting
        await db.execute(delete(EvalScore).where(EvalScore.eval_run_id == eval_run.id))
        await db.flush()

    # Insert dimension scores
    for dim in eval_result.dimensions:
        eval_score = EvalScore(
            eval_run_id=eval_run.id,
            trace_id=tid,
            dimension=dim.dimension,
            score=dim.score,
            reasoning=dim.reasoning,
        )
        db.add(eval_score)

    await db.commit()
    await db.refresh(eval_run)
    logger.info("Eval run saved: trace=%s overall=%.4f", trace_id, eval_run.overall_score)
    return eval_run


async def run_eval_batch(trace_ids: list[str], db: AsyncSession) -> list[EvalRun]:
    """Run evaluations for a list of trace_ids. Return all EvalRun results."""
    results = []
    for tid in trace_ids:
        try:
            run = await run_eval_for_trace(tid, db)
            results.append(run)
        except Exception as exc:
            logger.error("Eval failed for trace %s: %s", tid, exc)
    return results


async def run_eval_pending(db: AsyncSession, limit: int = 100) -> list[EvalRun]:
    """
    Find all traces that have no entry in eval_runs.
    Run evaluation for each.
    """
    stmt = text(
        """
        SELECT t.id FROM traces t
        LEFT JOIN eval_runs e ON t.id = e.trace_id
        WHERE e.id IS NULL
        LIMIT :limit
        """
    )
    result = await db.execute(stmt, {"limit": limit})
    pending_ids = [str(row[0]) for row in result.fetchall()]

    logger.info("Found %d unevaluated traces", len(pending_ids))
    return await run_eval_batch(pending_ids, db)


async def run_eval_for_trace_bg(trace_id: str) -> None:
    """
    Background-safe wrapper — creates its own DB session.
    Do NOT pass the request's db session here; it may be closed by the time
    this runs. Used by FastAPI BackgroundTasks.
    """
    try:
        async with AsyncSessionLocal() as db:
            await run_eval_for_trace(trace_id, db)
    except Exception as exc:
        logger.error("Background eval failed for trace %s: %s", trace_id, exc)
