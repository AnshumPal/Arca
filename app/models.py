import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Trace(Base):
    __tablename__ = "traces"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_id: Mapped[str] = mapped_column(Text, nullable=False, default="agent-1")
    input: Mapped[str] = mapped_column(Text, nullable=False)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_used: Mapped[str | None] = mapped_column(Text, nullable=True)
    tools_used: Mapped[list] = mapped_column(JSONB, default=list)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("traces.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    agent_id: Mapped[str] = mapped_column(String, nullable=False)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    eval_version: Mapped[str] = mapped_column(String, nullable=False, default="v1")

    scores: Mapped[list["EvalScore"]] = relationship(
        "EvalScore", back_populates="eval_run", cascade="all, delete-orphan"
    )
    trace: Mapped["Trace"] = relationship("Trace")


class EvalScore(Base):
    __tablename__ = "eval_scores"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    eval_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("eval_runs.id", ondelete="CASCADE"), nullable=False
    )
    trace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    dimension: Mapped[str] = mapped_column(String, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    eval_run: Mapped["EvalRun"] = relationship("EvalRun", back_populates="scores")
