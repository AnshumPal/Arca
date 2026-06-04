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
from app.models import (
    AgentVersion,
    EvalRun,
    EvalScore,
    OptimizerRun,
    Promotion,
    Rollback,
    SandboxAgent,
    SandboxEvalScore,
    SandboxTrace,
)
from app.optimizer import run_optimizer_cycle
from app.promoter import (
    PromoterError,
    approve_promotion,
    execute_rollback,
    reject_promotion,
    request_promotion,
)
from app.promotion_schemas import (
    AgentVersionOut,
    ApproveOut,
    GateCheckOut,
    GateResultOut,
    PromotionOut,
    PromotionSummary,
    RejectOut,
    RejectRequest,
    RollbackOut,
    RollbackRequest,
)
from app import version_manager
from app.optimizer_schemas import (
    FailurePatternOut,
    OptimizerRunDetail,
    OptimizerRunSummary,
    ProposalOut,
    ScheduleOut,
)
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
from app.scheduler import scheduler, start_scheduler, stop_scheduler
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
    start_scheduler()
    logger.info("Arca API starting up — env=%s agents=%d", settings.app_env, len(REGISTRY))
    yield
    stop_scheduler()
    logger.info("Arca API shutting down")


app = FastAPI(title="Arca", version="0.6.0", lifespan=lifespan)


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

    background_tasks.add_task(run_eval_for_trace_bg, str(trace_id))

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
        AgentOut(agent_id=aid, description=meta["description"])
        for aid, meta in REGISTRY.items()
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
                    DimensionScoreOut(dimension=s.dimension, score=s.score, reasoning=s.reasoning or "")
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
        SELECT er.agent_id, COUNT(er.id) AS traces_evaluated, AVG(er.overall_score) AS overall_avg,
               AVG(CASE WHEN es.dimension='latency'  THEN es.score END) AS latency_avg,
               AVG(CASE WHEN es.dimension='length'   THEN es.score END) AS length_avg,
               AVG(CASE WHEN es.dimension='feedback' THEN es.score END) AS feedback_avg,
               AVG(CASE WHEN es.dimension='error'    THEN es.score END) AS error_avg
        FROM eval_runs er JOIN eval_scores es ON es.eval_run_id = er.id
        GROUP BY er.agent_id ORDER BY er.agent_id
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
    return EvalReportOut(generated_at=datetime.now(timezone.utc), total_evaluated=total_evaluated, agents=agents)


@app.get("/eval/compare", response_model=EvalCompareOut)
async def eval_compare(
    agent_a: str = Query(...), agent_b: str = Query(...), db: AsyncSession = Depends(get_db),
) -> EvalCompareOut:
    async def agent_averages(aid: str) -> dict[str, float]:
        stmt = text(
            """
            SELECT AVG(er.overall_score) AS overall,
                   AVG(CASE WHEN es.dimension='latency'  THEN es.score END) AS latency,
                   AVG(CASE WHEN es.dimension='length'   THEN es.score END) AS length,
                   AVG(CASE WHEN es.dimension='feedback' THEN es.score END) AS feedback,
                   AVG(CASE WHEN es.dimension='error'    THEN es.score END) AS error
            FROM eval_runs er JOIN eval_scores es ON es.eval_run_id = er.id
            WHERE er.agent_id = :agent_id
            """
        )
        result = await db.execute(stmt, {"agent_id": aid})
        row = result.fetchone()
        if row is None or row.overall is None:
            return {"overall": 0.0, "latency": 0.0, "length": 0.0, "feedback": 0.0, "error": 0.0}
        return {k: round(float(getattr(row, k) or 0), 4) for k in ["overall", "latency", "length", "feedback", "error"]}

    avgs_a, avgs_b = await agent_averages(agent_a), await agent_averages(agent_b)
    comparison = {
        dim: ComparisonEntry(agent_a=avgs_a[dim], agent_b=avgs_b[dim], delta=round(avgs_a[dim] - avgs_b[dim], 4))
        for dim in ["overall", "latency", "length", "feedback", "error"]
    }
    d = avgs_a["overall"] - avgs_b["overall"]
    winner = "tied" if abs(d) <= 0.02 else (agent_a if d > 0 else agent_b)
    return EvalCompareOut(agent_a=agent_a, agent_b=agent_b, winner=winner, comparison=comparison)


@app.post("/eval/run", response_model=EvalRunResponse)
async def eval_run(body: EvalRunRequest, db: AsyncSession = Depends(get_db)) -> EvalRunResponse:
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
    return EvalRunResponse(evaluated=count, skipped=0, message=f"Evaluated {count} pending trace{'s' if count != 1 else ''}")


# ─── Phase 4 sandbox endpoints ─────────────────────────────────────────────────

@app.post("/sandbox", response_model=SandboxOut)
async def sandbox_create(body: SandboxCreateRequest, db: AsyncSession = Depends(get_db)) -> SandboxOut:
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
        sandbox_id=str(sandbox.id), name=sandbox.name,
        production_agent_id=sandbox.production_agent_id, status=sandbox.status,
        config=sandbox.config, trace_count=0, avg_overall_score=None, created_at=sandbox.created_at,
    )


@app.get("/sandbox", response_model=list[SandboxOut])
async def sandbox_list(
    status: str | None = Query(default=None),
    production_agent_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[SandboxOut]:
    sa_stmt = select(SandboxAgent).order_by(SandboxAgent.created_at.desc())
    if status:
        sa_stmt = sa_stmt.where(SandboxAgent.status == status)
    if production_agent_id:
        sa_stmt = sa_stmt.where(SandboxAgent.production_agent_id == production_agent_id)
    sa_result = await db.execute(sa_stmt)
    sandboxes = sa_result.scalars().all()

    output = []
    for sandbox in sandboxes:
        agg = await db.execute(
            text("SELECT COUNT(DISTINCT st.id) AS trace_count, AVG(ses.overall_score) AS avg_overall_score FROM sandbox_traces st LEFT JOIN sandbox_eval_scores ses ON ses.sandbox_id = st.sandbox_id WHERE st.sandbox_id = :sid"),
            {"sid": str(sandbox.id)},
        )
        row = agg.fetchone()
        output.append(SandboxOut(
            sandbox_id=str(sandbox.id), name=sandbox.name,
            production_agent_id=sandbox.production_agent_id, status=sandbox.status,
            config=sandbox.config or {}, trace_count=row.trace_count or 0 if row else 0,
            avg_overall_score=round(float(row.avg_overall_score), 4) if row and row.avg_overall_score else None,
            created_at=sandbox.created_at,
        ))
    return output


@app.get("/sandbox/{sandbox_id}", response_model=SandboxDetailOut)
async def sandbox_detail(sandbox_id: str, db: AsyncSession = Depends(get_db)) -> SandboxDetailOut:
    try:
        sid = uuid.UUID(sandbox_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid sandbox_id format")
    result = await db.execute(select(SandboxAgent).where(SandboxAgent.id == sid))
    sandbox = result.scalar_one_or_none()
    if sandbox is None:
        raise HTTPException(status_code=404, detail="Sandbox not found")
    agg_result = await db.execute(
        text("SELECT COUNT(DISTINCT st.id) AS trace_count, AVG(ses.overall_score) AS avg_overall_score, AVG(CASE WHEN ses.dimension='latency' THEN ses.score END) AS latency_avg, AVG(CASE WHEN ses.dimension='length' THEN ses.score END) AS length_avg, AVG(CASE WHEN ses.dimension='feedback' THEN ses.score END) AS feedback_avg, AVG(CASE WHEN ses.dimension='error' THEN ses.score END) AS error_avg FROM sandbox_traces st LEFT JOIN sandbox_eval_scores ses ON ses.sandbox_trace_id = st.id WHERE st.sandbox_id = :sid"),
        {"sid": str(sid)},
    )
    agg = agg_result.fetchone()
    def _r(v): return round(float(v), 4) if v is not None else 0.0
    return SandboxDetailOut(
        sandbox_id=str(sandbox.id), name=sandbox.name,
        production_agent_id=sandbox.production_agent_id, status=sandbox.status,
        config=sandbox.config or {}, trace_count=agg.trace_count or 0 if agg else 0,
        avg_overall_score=round(float(agg.avg_overall_score), 4) if agg and agg.avg_overall_score else None,
        dimension_averages={"latency": _r(agg.latency_avg), "length": _r(agg.length_avg), "feedback": _r(agg.feedback_avg), "error": _r(agg.error_avg)} if agg else None,
        created_at=sandbox.created_at,
    )


@app.get("/sandbox/{sandbox_id}/compare", response_model=SandboxCompareOut)
async def sandbox_compare(sandbox_id: str, db: AsyncSession = Depends(get_db)) -> SandboxCompareOut:
    try:
        data = await get_sandbox_comparison(sandbox_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return SandboxCompareOut(
        sandbox_id=data["sandbox_id"], sandbox_name=data["sandbox_name"],
        production_agent_id=data["production_agent_id"], verdict=data["verdict"],
        min_traces_required=data["min_traces_required"], sandbox_trace_count=data["sandbox_trace_count"],
        comparison={dim: ComparisonDimension(**vals) for dim, vals in data["comparison"].items()},
    )


@app.delete("/sandbox/{sandbox_id}", response_model=SandboxDeleteOut)
async def sandbox_delete(
    sandbox_id: str, action: str = Query(default="suspend"), db: AsyncSession = Depends(get_db),
) -> SandboxDeleteOut:
    if action not in ("suspend", "delete"):
        raise HTTPException(status_code=400, detail="action must be 'suspend' or 'delete'")
    try:
        sandbox = await (suspend_sandbox if action == "suspend" else delete_sandbox)(sandbox_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return SandboxDeleteOut(
        sandbox_id=str(sandbox.id), status=sandbox.status,
        message="Sandbox suspended. Shadow execution paused." if action == "suspend"
                else "Sandbox soft-deleted. Data retained for audit trail.",
    )


# ─── Phase 5 optimizer endpoints ──────────────────────────────────────────────

def _run_to_summary(run: OptimizerRun) -> OptimizerRunSummary:
    return OptimizerRunSummary(
        run_id=str(run.id),
        status=run.status,
        triggered_by=run.triggered_by,
        findings_count=len(run.findings or []),
        proposals_count=len(run.proposals or []),
        sandboxes_created=[str(s) for s in (run.sandboxes_created or [])],
        error=run.error,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


@app.post("/optimizer/run", response_model=OptimizerRunSummary)
async def optimizer_run(db: AsyncSession = Depends(get_db)) -> OptimizerRunSummary:
    """Manually trigger one optimizer cycle. Runs synchronously — returns when done."""
    run = await run_optimizer_cycle(db, triggered_by="manual")
    return _run_to_summary(run)


@app.get("/optimizer/runs", response_model=list[OptimizerRunSummary])
async def optimizer_runs_list(
    limit: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[OptimizerRunSummary]:
    """List all past optimizer runs."""
    stmt = select(OptimizerRun).order_by(OptimizerRun.started_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(OptimizerRun.status == status)
    result = await db.execute(stmt)
    runs = result.scalars().all()
    return [_run_to_summary(r) for r in runs]


@app.get("/optimizer/runs/{run_id}", response_model=OptimizerRunDetail)
async def optimizer_run_detail(run_id: str, db: AsyncSession = Depends(get_db)) -> OptimizerRunDetail:
    """Full detail of one optimizer run including findings and proposals."""
    try:
        rid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run_id format")
    result = await db.execute(select(OptimizerRun).where(OptimizerRun.id == rid))
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Optimizer run not found")

    findings = [FailurePatternOut(**f) for f in (run.findings or [])]
    proposals = [ProposalOut(**p) for p in (run.proposals or [])]

    return OptimizerRunDetail(
        run_id=str(run.id),
        status=run.status,
        triggered_by=run.triggered_by,
        agents_analyzed=run.agents_analyzed or [],
        findings_count=len(findings),
        proposals_count=len(proposals),
        sandboxes_created=[str(s) for s in (run.sandboxes_created or [])],
        error=run.error,
        started_at=run.started_at,
        completed_at=run.completed_at,
        findings=findings,
        proposals=proposals,
    )


@app.get("/optimizer/schedule", response_model=ScheduleOut)
async def optimizer_schedule(db: AsyncSession = Depends(get_db)) -> ScheduleOut:
    """Shows next scheduled run time and last run status."""
    next_run = None
    try:
        job = scheduler.get_job("nightly_optimizer")
        if job:
            next_run = job.next_run_time
    except Exception:
        pass

    result = await db.execute(
        select(OptimizerRun)
        .order_by(OptimizerRun.started_at.desc())
        .limit(1)
    )
    last = result.scalar_one_or_none()

    return ScheduleOut(
        next_run=next_run,
        last_run=_run_to_summary(last) if last else None,
        schedule="daily at 02:00 UTC",
    )


# ─── Phase 6 promotion gate + rollback endpoints ──────────────────────────────

def _promotion_to_out(p: Promotion) -> PromotionOut:
    """Build PromotionOut response with full gate detail."""
    gate_results = p.gate_results or {"passed": False, "summary": "", "checks": []}
    return PromotionOut(
        promotion_id=str(p.id),
        sandbox_id=str(p.sandbox_id),
        agent_id=p.agent_id,
        status=p.status,
        gate_passed=p.gate_passed,
        gate_results=GateResultOut(
            passed=gate_results.get("passed", False),
            summary=gate_results.get("summary", ""),
            checks=[GateCheckOut(**c) for c in gate_results.get("checks", [])],
        ),
        requested_at=p.requested_at,
        decided_at=p.decided_at,
        decided_by=p.decided_by,
        rejection_reason=p.rejection_reason,
        version_created=p.version_created,
    )


@app.post("/promote/{sandbox_id}", response_model=PromotionOut)
async def promote_sandbox(
    sandbox_id: str,
    db: AsyncSession = Depends(get_db),
) -> PromotionOut:
    """Request promotion for a sandbox. Runs gate automatically — does NOT block on gate failure."""
    try:
        promotion = await request_promotion(sandbox_id, db)
    except PromoterError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    return _promotion_to_out(promotion)


@app.get("/promote", response_model=list[PromotionSummary])
async def promote_list(
    status: str | None = Query(default=None),
    agent_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[PromotionSummary]:
    """List all promotion records."""
    stmt = select(Promotion).order_by(Promotion.requested_at.desc())
    if status:
        stmt = stmt.where(Promotion.status == status)
    if agent_id:
        stmt = stmt.where(Promotion.agent_id == agent_id)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [
        PromotionSummary(
            promotion_id=str(p.id),
            sandbox_id=str(p.sandbox_id),
            agent_id=p.agent_id,
            status=p.status,
            gate_passed=p.gate_passed,
            requested_at=p.requested_at,
            decided_at=p.decided_at,
            version_created=p.version_created,
        )
        for p in rows
    ]


@app.get("/promote/{promotion_id}", response_model=PromotionOut)
async def promote_detail(
    promotion_id: str,
    db: AsyncSession = Depends(get_db),
) -> PromotionOut:
    """Full detail of one promotion including all gate check results."""
    try:
        pid = uuid.UUID(promotion_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid promotion_id format")

    result = await db.execute(select(Promotion).where(Promotion.id == pid))
    promotion = result.scalar_one_or_none()
    if promotion is None:
        raise HTTPException(status_code=404, detail="Promotion not found")
    return _promotion_to_out(promotion)


@app.post("/promote/{promotion_id}/approve", response_model=ApproveOut)
async def promote_approve(
    promotion_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApproveOut:
    """Human approves promotion. Agent goes live on new prompt within 30 seconds."""
    try:
        promotion = await approve_promotion(promotion_id, db)
    except PromoterError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    return ApproveOut(
        promotion_id=str(promotion.id),
        status=promotion.status,
        agent_id=promotion.agent_id,
        version_created=promotion.version_created or 0,
        decided_at=promotion.decided_at or datetime.now(timezone.utc),
        message=f"{promotion.agent_id} promoted to version {promotion.version_created}. Live within 30 seconds.",
    )


@app.post("/promote/{promotion_id}/reject", response_model=RejectOut)
async def promote_reject(
    promotion_id: str,
    body: RejectRequest,
    db: AsyncSession = Depends(get_db),
) -> RejectOut:
    """Human rejects promotion. Sandbox stays active."""
    try:
        promotion = await reject_promotion(promotion_id, body.reason, db)
    except PromoterError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    return RejectOut(
        promotion_id=str(promotion.id),
        status=promotion.status,
        agent_id=promotion.agent_id,
        rejection_reason=promotion.rejection_reason or "",
        decided_at=promotion.decided_at or datetime.now(timezone.utc),
    )


@app.get("/agents/{agent_id}/versions", response_model=list[AgentVersionOut])
async def agent_versions(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[AgentVersionOut]:
    """Full version history for a production agent."""
    if agent_id not in REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {agent_id}")
    versions = await version_manager.get_version_history(agent_id, db)
    return [
        AgentVersionOut(
            version=v.version,
            is_current=v.is_current,
            system_prompt=v.system_prompt,
            promoted_from=str(v.promoted_from) if v.promoted_from else None,
            created_at=v.created_at,
        )
        for v in versions
    ]


@app.post("/agents/{agent_id}/rollback", response_model=RollbackOut)
async def agent_rollback(
    agent_id: str,
    body: RollbackRequest,
    db: AsyncSession = Depends(get_db),
) -> RollbackOut:
    """Roll back a production agent to a previous version."""
    if agent_id not in REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {agent_id}")
    try:
        rb = await execute_rollback(agent_id, body.to_version, body.reason, db)
    except PromoterError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    return RollbackOut(
        rollback_id=str(rb.id),
        agent_id=rb.agent_id,
        from_version=rb.from_version,
        to_version=rb.to_version,
        reason=rb.reason,
        rolled_back_at=rb.rolled_back_at,
        message=f"{agent_id} rolled back to version {rb.to_version}. Live within 30 seconds.",
    )


@app.get("/rollbacks", response_model=list[RollbackOut])
async def rollbacks_list(
    agent_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[RollbackOut]:
    """List all rollback events."""
    stmt = select(Rollback).order_by(Rollback.rolled_back_at.desc())
    if agent_id:
        stmt = stmt.where(Rollback.agent_id == agent_id)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [
        RollbackOut(
            rollback_id=str(rb.id),
            agent_id=rb.agent_id,
            from_version=rb.from_version,
            to_version=rb.to_version,
            reason=rb.reason,
            rolled_back_at=rb.rolled_back_at,
            message=f"{rb.agent_id} rolled back from v{rb.from_version} to v{rb.to_version}",
        )
        for rb in rows
    ]
