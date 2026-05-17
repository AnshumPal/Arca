import logging
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app import orchestrator, tracer
from app.agents import REGISTRY
from app.config import settings
from app.database import get_db
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


app = FastAPI(title="Arca", version="0.2.0", lifespan=lifespan)


# ─── Phase 1 endpoints (unchanged behaviour) ──────────────────────────────────

@app.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, db: AsyncSession = Depends(get_db)) -> ChatResponse:
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
