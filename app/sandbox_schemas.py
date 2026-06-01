from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator


class SandboxConfig(BaseModel):
    system_prompt: Optional[str] = None
    model:         Optional[str] = None
    temperature:   Optional[float] = None

    @field_validator("temperature")
    @classmethod
    def temperature_range(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (0.0 <= v <= 2.0):
            raise ValueError("temperature must be between 0.0 and 2.0")
        return v


class SandboxCreateRequest(BaseModel):
    name:                str
    production_agent_id: str
    config:              SandboxConfig = SandboxConfig()


class SandboxOut(BaseModel):
    sandbox_id:        str
    name:              str
    production_agent_id: str
    status:            str
    config:            dict
    trace_count:       int = 0
    avg_overall_score: Optional[float] = None
    created_at:        datetime


class SandboxDetailOut(SandboxOut):
    dimension_averages: Optional[dict] = None


class ComparisonDimension(BaseModel):
    production: float
    sandbox:    float
    delta:      float


class SandboxCompareOut(BaseModel):
    sandbox_id:          str
    sandbox_name:        str
    production_agent_id: str
    verdict:             str
    min_traces_required: int
    sandbox_trace_count: int
    comparison:          dict[str, ComparisonDimension]


class SandboxDeleteOut(BaseModel):
    sandbox_id: str
    status:     str
    message:    str
