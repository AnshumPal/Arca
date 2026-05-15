import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app import orchestrator, tracer
from app.agent import AGENT_ID
from app.database import get_db
from app.schemas import (
    ChatRequest,
    ChatResponse,
    FeedbackRequest,
    FeedbackResponse,
    ReportResponse,
    TraceOut,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Arca API starting up")
    yield
    logger.info("Arca API shutting down")


app = FastAPI(title="Arca", version="0.1.0", lifespan=lifespan)


@app.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, db: AsyncSession = Depends(get_db)) -> ChatResponse:
    start_time = time.time()
    response_text: str | None = None
    error: str | None = None
    prompt_used: str | None = None

    try:
        response_text, prompt_used = await orchestrator.handle(body.message, body.session_id)
    except Exception as exc:
        error = str(exc)
        logger.error("Agent error: %s", error)

    latency_ms = int((time.time() - start_time) * 1000)

    trace_id = await tracer.write_trace(
        db,
        session_id=body.session_id,
        agent_id=AGENT_ID,
        input=body.message,
        output=response_text,
        prompt_used=prompt_used,
        latency_ms=latency_ms,
        error=error,
    )

    if error:
        raise HTTPException(status_code=500, detail=error)

    return ChatResponse(response=response_text, trace_id=trace_id, latency_ms=latency_ms)


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
