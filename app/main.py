import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app import orchestrator, tracer
from app.agents import REGISTRY
from app.config import settings
from app.database import get_db
from app.eval_runner import run_eval_for_trace, run_eval_for_trace_bg, run_eval_pending
from app.eval_schemas import (
    AgentDimensionAvg,
    AgentReportEntry,
    ComparisonEntry,
    EvalCompareOut,
    EvalReportOut,
    EvalRunRequest,
    EvalRunResponse,
    EvalScoreOut,
    DimensionScoreOut,
)
from app.models import EvalRun, EvalScore
from app.schemas import (
    AgentOut,
    ChatRequest,
    ChatResponse,
    FeedbackRequest,
    FeedbackResponse,
    HealthOut,
    ReportResponse,
    TraceOut,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Arca API starting up — env=%s agents=%d", settings.app_env, len(REGISTRY))
    yield
    logger.info("Arca API shutting down")


app = FastAPI(title="Arca", version="0.3.0", lifespan=lifespan)


# ─── Phase 1 endpoints (unchanged behaviour) ──────────────────────────────────

@app.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    start_time = time.time()
    response_text: str | None = None
    error: str | None = None
    prompt_used: str | None = None
    agent_id: str = "agent-1"  # default — overwritten on success

    try:
        result = await orchestrator.handle(body.message, body.session_id)
        response_text = result["response"]
        prompt_used = result["prompt_used"]
        agent_id = result["agent_id"]
    except Exception as exc:
        error = str(exc)
        logger.error("Agent error: %s", error)

    latency_ms = int((time.time() - start_time) * 1000)

    trace_id = await tracer.write_trace(
        db,
        session_id=body.session_id,
        agent_id=agent_id,
        input=body.message,
        output=response_text,
        prompt_used=prompt_used,
        latency_ms=latency_ms,
        error=error,
    )

    # Trigger background evaluation — user never waits for this
    background_tasks.add_task(run_eval_for_trace_bg, str(trace_id))

    if error:
        raise HTTPException(status_code=500, detail=error)

    return ChatResponse(
        response=response_text,
        trace_id=trace_id,
        agent_id=agent_id,
        latency_ms=latency_ms,
    )


@app.post("/feedback", response_model=FeedbackResponse)
async def feedback(body: FeedbackRequest, db: AsyncSession = Depends(get_db)) -> FeedbackResponse:
    updated = await tracer.update_feedback(db, body.trace_id, body.feedback)
    if not updated:
        raise HTTPException(status_code=404, detail="Trace not found")
    return FeedbackResponse()


@app.get("/traces", response_model=list[TraceOut])
async def list_traces(
    limit: int = Query(default=20, ge=1, le=100),
    session_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[TraceOut]:
    return await tracer.get_traces(db, limit=limit, session_id=session_id)


@app.get("/report", response_model=ReportResponse)
async def report(db: AsyncSession = Depends(get_db)) -> ReportResponse:
    return await tracer.get_report(db)


# ─── Phase 2 endpoints ────────────────────────────────────────────────────────

@app.get("/agents", response_model=list[AgentOut])
async def list_agents() -> list[AgentOut]:
    """Returns all registered agents with their IDs and descriptions."""
    return [
        AgentOut(agent_id=agent_id, description=meta["description"])
        for agent_id, meta in REGISTRY.items()
    ]


@app.get("/health", response_model=HealthOut)
async def health() -> HealthOut:
    """Health check — used by Cloud Run and load balancers."""
    return HealthOut(
        status="ok",
        env=settings.app_env,
        agents_active=len(REGISTRY),
    )


# ─── Phase 3 eval endpoints ────────────────────────────────────────────────────

@app.get("/eval/scores", response_model=list[EvalScoreOut])
async def eval_scores(
    agent_id: str | None = Query(default=None),
    dimension: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    min_score: float | None = Query(default=None, ge=0.0, le=1.0),
    max_score: float | None = Query(default=None, ge=0.0, le=1.0),
    db: AsyncSession = Depends(get_db),
) -> list[EvalScoreOut]:
    """Returns evaluation scores, filterable by agent, dimension, and score range."""

    # Base query: fetch eval_runs with optional agent filter
    runs_stmt = select(EvalRun).order_by(EvalRun.evaluated_at.desc()).limit(limit)
    if agent_id:
        runs_stmt = runs_stmt.where(EvalRun.agent_id == agent_id)

    runs_result = await db.execute(runs_stmt)
    runs = runs_result.scalars().all()

    output: list[EvalScoreOut] = []
    for run in runs:
        # Fetch dimension scores for this run
        scores_stmt = select(EvalScore).where(EvalScore.eval_run_id == run.id)
        if dimension:
            scores_stmt = scores_stmt.where(EvalScore.dimension == dimension)
        if min_score is not None:
            scores_stmt = scores_stmt.where(EvalScore.score >= min_score)
        if max_score is not None:
            scores_stmt = scores_stmt.where(EvalScore.score <= max_score)

        scores_result = await db.execute(scores_stmt)
        scores = scores_result.scalars().all()

        # Skip this run if all its dimension scores were filtered out
        if not scores:
            continue

        output.append(
            EvalScoreOut(
                trace_id=str(run.trace_id),
                agent_id=run.agent_id,
                overall_score=run.overall_score,
                evaluated_at=run.evaluated_at,
                dimensions=[
                    DimensionScoreOut(
                        dimension=s.dimension,
                        score=s.score,
                        reasoning=s.reasoning or "",
                    )
                    for s in scores
                ],
            )
        )

    return output


@app.get("/eval/report", response_model=EvalReportOut)
async def eval_report(db: AsyncSession = Depends(get_db)) -> EvalReportOut:
    """Per-agent scorecard — averages computed via SQL aggregates."""

    # Total evaluated traces
    total_result = await db.execute(select(func.count()).select_from(EvalRun))
    total_evaluated = total_result.scalar() or 0

    # Per-agent overall averages
    agent_stmt = text(
        """
        SELECT
            er.agent_id,
            COUNT(er.id)                                     AS traces_evaluated,
            AVG(er.overall_score)                            AS overall_avg,
            AVG(CASE WHEN es.dimension = 'latency'  THEN es.score END) AS latency_avg,
            AVG(CASE WHEN es.dimension = 'length'   THEN es.score END) AS length_avg,
            AVG(CASE WHEN es.dimension = 'feedback' THEN es.score END) AS feedback_avg,
            AVG(CASE WHEN es.dimension = 'error'    THEN es.score END) AS error_avg
        FROM eval_runs er
        JOIN eval_scores es ON es.eval_run_id = er.id
        GROUP BY er.agent_id
        ORDER BY er.agent_id
        """
    )
    result = await db.execute(agent_stmt)
    rows = result.fetchall()

    agents = [
        AgentReportEntry(
            agent_id=row.agent_id,
            traces_evaluated=row.traces_evaluated,
            overall_avg=round(float(row.overall_avg), 4),
            dimensions=AgentDimensionAvg(
                latency=round(float(row.latency_avg or 0), 4),
                length=round(float(row.length_avg or 0), 4),
                feedback=round(float(row.feedback_avg or 0), 4),
                error=round(float(row.error_avg or 0), 4),
            ),
        )
        for row in rows
    ]

    return EvalReportOut(
        generated_at=datetime.now(timezone.utc),
        total_evaluated=total_evaluated,
        agents=agents,
    )


@app.get("/eval/compare", response_model=EvalCompareOut)
async def eval_compare(
    agent_a: str = Query(...),
    agent_b: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> EvalCompareOut:
    """Side-by-side comparison of two agents across all dimensions."""

    async def agent_averages(aid: str) -> dict[str, float]:
        stmt = text(
            """
            SELECT
                AVG(er.overall_score)                            AS overall,
                AVG(CASE WHEN es.dimension = 'latency'  THEN es.score END) AS latency,
                AVG(CASE WHEN es.dimension = 'length'   THEN es.score END) AS length,
                AVG(CASE WHEN es.dimension = 'feedback' THEN es.score END) AS feedback,
                AVG(CASE WHEN es.dimension = 'error'    THEN es.score END) AS error
            FROM eval_runs er
            JOIN eval_scores es ON es.eval_run_id = er.id
            WHERE er.agent_id = :agent_id
            """
        )
        result = await db.execute(stmt, {"agent_id": aid})
        row = result.fetchone()
        if row is None or row.overall is None:
            return {"overall": 0.0, "latency": 0.0, "length": 0.0, "feedback": 0.0, "error": 0.0}
        return {
            "overall":  round(float(row.overall  or 0), 4),
            "latency":  round(float(row.latency  or 0), 4),
            "length":   round(float(row.length   or 0), 4),
            "feedback": round(float(row.feedback or 0), 4),
            "error":    round(float(row.error    or 0), 4),
        }

    avgs_a = await agent_averages(agent_a)
    avgs_b = await agent_averages(agent_b)

    comparison: dict[str, ComparisonEntry] = {
        dim: ComparisonEntry(
            agent_a=avgs_a[dim],
            agent_b=avgs_b[dim],
            delta=round(avgs_a[dim] - avgs_b[dim], 4),
        )
        for dim in ["overall", "latency", "length", "feedback", "error"]
    }

    delta_overall = avgs_a["overall"] - avgs_b["overall"]
    if abs(delta_overall) <= 0.02:
        winner = "tied"
    elif delta_overall > 0:
        winner = agent_a
    else:
        winner = agent_b

    return EvalCompareOut(
        agent_a=agent_a,
        agent_b=agent_b,
        winner=winner,
        comparison=comparison,
    )


@app.post("/eval/run", response_model=EvalRunResponse)
async def eval_run(
    body: EvalRunRequest,
    db: AsyncSession = Depends(get_db),
) -> EvalRunResponse:
    """Manually trigger evaluation on a specific trace or all pending traces."""

    if body.trace_id:
        try:
            await run_eval_for_trace(body.trace_id, db)
            return EvalRunResponse(evaluated=1, skipped=0, message=f"Evaluated trace {body.trace_id}")
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except Exception as exc:
            logger.error("Manual eval failed: %s", exc)
            raise HTTPException(status_code=500, detail="Evaluation failed")

    # No trace_id — evaluate all pending
    runs = await run_eval_pending(db)
    count = len(runs)
    return EvalRunResponse(
        evaluated=count,
        skipped=0,
        message=f"Evaluated {count} pending trace{'s' if count != 1 else ''}",
    )
