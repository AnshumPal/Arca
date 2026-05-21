from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class DimensionScoreOut(BaseModel):
    dimension: str
    score: float
    reasoning: str


class EvalScoreOut(BaseModel):
    trace_id: str
    agent_id: str
    overall_score: float
    evaluated_at: datetime
    dimensions: list[DimensionScoreOut]


class AgentDimensionAvg(BaseModel):
    latency:  float
    length:   float
    feedback: float
    error:    float


class AgentReportEntry(BaseModel):
    agent_id:         str
    traces_evaluated: int
    overall_avg:      float
    dimensions:       AgentDimensionAvg


class EvalReportOut(BaseModel):
    generated_at:    datetime
    total_evaluated: int
    agents:          list[AgentReportEntry]


class ComparisonEntry(BaseModel):
    agent_a: float
    agent_b: float
    delta:   float


class EvalCompareOut(BaseModel):
    agent_a:    str
    agent_b:    str
    winner:     str
    comparison: dict[str, ComparisonEntry]


class EvalRunRequest(BaseModel):
    trace_id: Optional[str] = None


class EvalRunResponse(BaseModel):
    evaluated: int
    skipped:   int
    message:   str
