import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    response: str
    trace_id: uuid.UUID
    latency_ms: int


class FeedbackRequest(BaseModel):
    trace_id: uuid.UUID
    feedback: Literal[1, -1]


class FeedbackResponse(BaseModel):
    status: str = "ok"


class TraceOut(BaseModel):
    id: uuid.UUID
    session_id: str | None
    agent_id: str
    input: str
    output: str | None
    latency_ms: int | None
    feedback: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class FeedbackSummary(BaseModel):
    positive: int
    negative: int
    none: int


class ReportResponse(BaseModel):
    total_traces: int
    avg_latency_ms: float | None
    error_count: int
    feedback: FeedbackSummary
    generated_at: datetime
