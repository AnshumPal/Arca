import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Trace
from app.schemas import FeedbackSummary, ReportResponse, TraceOut

logger = logging.getLogger(__name__)


async def write_trace(
    db: AsyncSession,
    *,
    session_id: str | None,
    agent_id: str,
    input: str,
    output: str | None = None,
    prompt_used: str | None = None,
    latency_ms: int | None = None,
    error: str | None = None,
) -> uuid.UUID:
    trace = Trace(
        session_id=session_id,
        agent_id=agent_id,
        input=input,
        output=output,
        prompt_used=prompt_used,
        tools_used=[],
        latency_ms=latency_ms,
        error=error,
    )
    db.add(trace)
    await db.commit()
    await db.refresh(trace)
    logger.info("Trace written: %s", trace.id)
    return trace.id


async def get_traces(
    db: AsyncSession,
    *,
    limit: int = 20,
    session_id: str | None = None,
) -> list[TraceOut]:
    stmt = select(Trace).order_by(Trace.created_at.desc()).limit(limit)
    if session_id:
        stmt = stmt.where(Trace.session_id == session_id)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [TraceOut.model_validate(row) for row in rows]


async def update_feedback(db: AsyncSession, trace_id: uuid.UUID, feedback: int) -> bool:
    result = await db.execute(select(Trace).where(Trace.id == trace_id))
    trace = result.scalar_one_or_none()
    if trace is None:
        return False
    trace.feedback = feedback
    await db.commit()
    return True


async def get_report(db: AsyncSession) -> ReportResponse:
    total_result = await db.execute(select(func.count()).select_from(Trace))
    total = total_result.scalar() or 0

    avg_result = await db.execute(select(func.avg(Trace.latency_ms)).select_from(Trace))
    avg_latency = avg_result.scalar()

    error_result = await db.execute(
        select(func.count()).select_from(Trace).where(Trace.error.isnot(None))
    )
    error_count = error_result.scalar() or 0

    pos_result = await db.execute(
        select(func.count()).select_from(Trace).where(Trace.feedback == 1)
    )
    positive = pos_result.scalar() or 0

    neg_result = await db.execute(
        select(func.count()).select_from(Trace).where(Trace.feedback == -1)
    )
    negative = neg_result.scalar() or 0

    none_result = await db.execute(
        select(func.count()).select_from(Trace).where(Trace.feedback.is_(None))
    )
    none_count = none_result.scalar() or 0

    return ReportResponse(
        total_traces=total,
        avg_latency_ms=float(avg_latency) if avg_latency is not None else None,
        error_count=error_count,
        feedback=FeedbackSummary(positive=positive, negative=negative, none=none_count),
        generated_at=datetime.now(timezone.utc),
    )
