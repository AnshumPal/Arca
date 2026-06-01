from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class FailurePatternOut(BaseModel):
    agent_id:      str
    dimension:     str
    avg_score:     float
    threshold:     float
    sample_count:  int
    sample_inputs: list[str]
    diagnosis:     str


class ProposalOut(BaseModel):
    agent_id:        str
    dimension:       str
    original_prompt: str
    proposed_prompt: str
    reasoning:       str
    sandbox_config:  dict


class OptimizerRunSummary(BaseModel):
    run_id:            str
    status:            str
    triggered_by:      str
    findings_count:    int
    proposals_count:   int
    sandboxes_created: list[str]
    error:             Optional[str] = None
    started_at:        datetime
    completed_at:      Optional[datetime] = None


class OptimizerRunDetail(OptimizerRunSummary):
    agents_analyzed: list[str]
    findings:        list[FailurePatternOut]
    proposals:       list[ProposalOut]


class ScheduleOut(BaseModel):
    next_run: Optional[datetime]
    last_run: Optional[OptimizerRunSummary]
    schedule: str
