import logging
import time
import uuid
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
    DimensionScoreOut,
    EvalCompareOut,
    EvalReportOut,
    EvalRunRequest,
    EvalRunResponse,
    EvalScoreOut,
)
from app.models import EvalRun, EvalScore, SandboxAgent, SandboxEvalScore, SandboxTrace
from app.sandbox import (
    create_sandbox,
    delete_sandbox,
    get_active_sandboxes_for_agent,
    get_sandbox_comparison,
    run_sandbox_shadow_bg,
    suspend_sandbox,
)
from app.sandbox_schemas import (
    ComparisonDimension,
    SandboxCompareOut,
    SandboxCreateRequest,
    SandboxDeleteOut,
    SandboxDetailOut,
    SandboxOut,
)
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


app = FastAPI(title="Arca", version="0.4.0", lifespan=lifespan)


# ─── Phase 1 endpoints ────────────────────────────────────────────────────────

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
    agent_id: str = "agent-1"

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

    # Phase 3: background eval
    background_tasks.add_task(run_eval_for_trace_bg, str(trace_id))

    # Phase 4: shadow execution for all active sandboxes matching this agent
    active_sandboxes = await get_active_sandboxes_for_agent(agent_id, db)
    for sandbox in active_sandboxes:
        background_tasks.add_task(
            run_sandbox_shadow_bg,
            str(sandbox.id),
            body.message,
            body.session_id or "",
        )

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
    return [
        AgentOut(agent_id=agent_id, description=meta["description"])
        for agent_id, meta in REGISTRY.items()
    ]


@app.get("/health", response_model=HealthOut)
async def health() -> HealthOut:
    return HealthOut(status="ok", env=settings.app_env, agents_active=len(REGISTRY))


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
    runs_stmt = select(EvalRun).order_by(EvalRun.evaluated_at.desc()).limit(limit)
    if agent_id:
        runs_stmt = runs_stmt.where(EvalRun.agent_id == agent_id)
    runs_result = await db.execute(runs_stmt)
    runs = runs_result.scalars().all()

    output: list[EvalScoreOut] = []
    for run in runs:
        scores_stmt = select(EvalScore).where(EvalScore.eval_run_id == run.id)
        if dimension:
            scores_stmt = scores_stmt.where(EvalScore.dimension == dimension)
        if min_score is not None:
            scores_stmt = scores_stmt.where(EvalScore.score >= min_score)
        if max_score is not None:
            scores_stmt = scores_stmt.where(EvalScore.score <= max_score)
        scores_result = await db.execute(scores_stmt)
        scores = scores_result.scalars().all()
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
    total_result = await db.execute(select(func.count()).select_from(EvalRun))
    total_evaluated = total_result.scalar() or 0

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
    winner = "tied" if abs(delta_overall) <= 0.02 else (agent_a if delta_overall > 0 else agent_b)

    return EvalCompareOut(agent_a=agent_a, agent_b=agent_b, winner=winner, comparison=comparison)


@app.post("/eval/run", response_model=EvalRunResponse)
async def eval_run(
    body: EvalRunRequest,
    db: AsyncSession = Depends(get_db),
) -> EvalRunResponse:
    if body.trace_id:
        try:
            await run_eval_for_trace(body.trace_id, db)
            return EvalRunResponse(evaluated=1, skipped=0, message=f"Evaluated trace {body.trace_id}")
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except Exception as exc:
            logger.error("Manual eval failed: %s", exc)
            raise HTTPException(status_code=500, detail="Evaluation failed")

    runs = await run_eval_pending(db)
    count = len(runs)
    return EvalRunResponse(
        evaluated=count,
        skipped=0,
        message=f"Evaluated {count} pending trace{'s' if count != 1 else ''}",
    )


# ─── Phase 4 sandbox endpoints ─────────────────────────────────────────────────

@app.post("/sandbox", response_model=SandboxOut)
async def sandbox_create(
    body: SandboxCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> SandboxOut:
    """Create a new sandbox copy of a production agent."""
    if body.production_agent_id not in REGISTRY:
        raise HTTPException(status_code=400, detail=f"Unknown agent: {body.production_agent_id}")

    try:
        sandbox = await create_sandbox(
            name=body.name,
            production_agent_id=body.production_agent_id,
            config=body.config.model_dump(exclude_none=True),
            db=db,
        )
    except NameError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return SandboxOut(
        sandbox_id=str(sandbox.id),
        name=sandbox.name,
        production_agent_id=sandbox.production_agent_id,
        status=sandbox.status,
        config=sandbox.config,
        trace_count=0,
        avg_overall_score=None,
        created_at=sandbox.created_at,
    )


@app.get("/sandbox", response_model=list[SandboxOut])
async def sandbox_list(
    status: str | None = Query(default=None),
    production_agent_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[SandboxOut]:
    """List all sandbox agents with trace count and avg score (SQL aggregates)."""
    # Use ORM query for filters (avoids asyncpg NULL type inference issue)
    sa_stmt = select(SandboxAgent).order_by(SandboxAgent.created_at.desc())
    if status:
        sa_stmt = sa_stmt.where(SandboxAgent.status == status)
    if production_agent_id:
        sa_stmt = sa_stmt.where(SandboxAgent.production_agent_id == production_agent_id)

    sa_result = await db.execute(sa_stmt)
    sandboxes = sa_result.scalars().all()

    output = []
    for sandbox in sandboxes:
        # SQL aggregate per sandbox
        agg = await db.execute(
            text(
                """
                SELECT COUNT(DISTINCT st.id) AS trace_count,
                       AVG(ses.overall_score) AS avg_overall_score
                FROM sandbox_traces st
                LEFT JOIN sandbox_eval_scores ses ON ses.sandbox_id = st.sandbox_id
                WHERE st.sandbox_id = :sid
                """
            ),
            {"sid": str(sandbox.id)},
        )
        row = agg.fetchone()
        output.append(
            SandboxOut(
                sandbox_id=str(sandbox.id),
                name=sandbox.name,
                production_agent_id=sandbox.production_agent_id,
                status=sandbox.status,
                config=sandbox.config or {},
                trace_count=row.trace_count or 0 if row else 0,
                avg_overall_score=round(float(row.avg_overall_score), 4) if row and row.avg_overall_score else None,
                created_at=sandbox.created_at,
            )
        )
    return output


@app.get("/sandbox/{sandbox_id}", response_model=SandboxDetailOut)
async def sandbox_detail(
    sandbox_id: str,
    db: AsyncSession = Depends(get_db),
) -> SandboxDetailOut:
    """Full details for one sandbox including per-dimension averages."""
    try:
        sid = uuid.UUID(sandbox_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid sandbox_id format")

    result = await db.execute(select(SandboxAgent).where(SandboxAgent.id == sid))
    sandbox = result.scalar_one_or_none()
    if sandbox is None:
        raise HTTPException(status_code=404, detail="Sandbox not found")

    # Trace count + overall avg
    agg_stmt = text(
        """
        SELECT
            COUNT(DISTINCT st.id)  AS trace_count,
            AVG(ses.overall_score) AS avg_overall_score,
            AVG(CASE WHEN ses.dimension = 'latency'  THEN ses.score END) AS latency_avg,
            AVG(CASE WHEN ses.dimension = 'length'   THEN ses.score END) AS length_avg,
            AVG(CASE WHEN ses.dimension = 'feedback' THEN ses.score END) AS feedback_avg,
            AVG(CASE WHEN ses.dimension = 'error'    THEN ses.score END) AS error_avg
        FROM sandbox_traces st
        LEFT JOIN sandbox_eval_scores ses ON ses.sandbox_trace_id = st.id
        WHERE st.sandbox_id = :sid
        """
    )
    agg_result = await db.execute(agg_stmt, {"sid": str(sid)})
    agg = agg_result.fetchone()

    def _r(val) -> float:
        return round(float(val), 4) if val is not None else 0.0

    dimension_averages = {
        "latency":  _r(agg.latency_avg),
        "length":   _r(agg.length_avg),
        "feedback": _r(agg.feedback_avg),
        "error":    _r(agg.error_avg),
    } if agg else None

    return SandboxDetailOut(
        sandbox_id=str(sandbox.id),
        name=sandbox.name,
        production_agent_id=sandbox.production_agent_id,
        status=sandbox.status,
        config=sandbox.config or {},
        trace_count=agg.trace_count or 0 if agg else 0,
        avg_overall_score=round(float(agg.avg_overall_score), 4) if agg and agg.avg_overall_score else None,
        dimension_averages=dimension_averages,
        created_at=sandbox.created_at,
    )


@app.get("/sandbox/{sandbox_id}/compare", response_model=SandboxCompareOut)
async def sandbox_compare(
    sandbox_id: str,
    db: AsyncSession = Depends(get_db),
) -> SandboxCompareOut:
    """Compare sandbox eval scores vs its production baseline."""
    try:
        data = await get_sandbox_comparison(sandbox_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    comparison = {
        dim: ComparisonDimension(**vals)
        for dim, vals in data["comparison"].items()
    }

    return SandboxCompareOut(
        sandbox_id=data["sandbox_id"],
        sandbox_name=data["sandbox_name"],
        production_agent_id=data["production_agent_id"],
        verdict=data["verdict"],
        min_traces_required=data["min_traces_required"],
        sandbox_trace_count=data["sandbox_trace_count"],
        comparison=comparison,
    )


@app.delete("/sandbox/{sandbox_id}", response_model=SandboxDeleteOut)
async def sandbox_delete(
    sandbox_id: str,
    action: str = Query(default="suspend"),
    db: AsyncSession = Depends(get_db),
) -> SandboxDeleteOut:
    """Suspend or soft-delete a sandbox. action=suspend|delete (default: suspend)."""
    if action not in ("suspend", "delete"):
        raise HTTPException(status_code=400, detail="action must be 'suspend' or 'delete'")

    try:
        if action == "suspend":
            sandbox = await suspend_sandbox(sandbox_id, db)
            message = "Sandbox suspended. Shadow execution paused."
        else:
            sandbox = await delete_sandbox(sandbox_id, db)
            message = "Sandbox soft-deleted. Data retained for audit trail."
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return SandboxDeleteOut(
        sandbox_id=str(sandbox.id),
        status=sandbox.status,
        message=message,
    )
