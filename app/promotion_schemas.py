from datetime import datetime
from typing import Optional, Union

from pydantic import BaseModel


class GateCheckOut(BaseModel):
    name:      str
    passed:    bool
    value:     Union[float, int, str]
    threshold: Union[float, int, str]
    message:   str


class GateResultOut(BaseModel):
    passed:  bool
    summary: str
    checks:  list[GateCheckOut]


class PromotionOut(BaseModel):
    promotion_id:     str
    sandbox_id:       str
    agent_id:         str
    status:           str
    gate_passed:      Optional[bool]
    gate_results:     GateResultOut
    requested_at:     datetime
    decided_at:       Optional[datetime] = None
    decided_by:       Optional[str] = None
    rejection_reason: Optional[str] = None
    version_created:  Optional[int] = None


class PromotionSummary(BaseModel):
    promotion_id:    str
    sandbox_id:      str
    agent_id:        str
    status:          str
    gate_passed:     Optional[bool]
    requested_at:    datetime
    decided_at:      Optional[datetime] = None
    version_created: Optional[int] = None


class ApproveOut(BaseModel):
    promotion_id:    str
    status:          str
    agent_id:        str
    version_created: int
    decided_at:      datetime
    message:         str


class RejectRequest(BaseModel):
    reason: str


class RejectOut(BaseModel):
    promotion_id:     str
    status:           str
    agent_id:         str
    rejection_reason: str
    decided_at:       datetime


class AgentVersionOut(BaseModel):
    version:       int
    is_current:    bool
    system_prompt: str
    promoted_from: Optional[str] = None
    created_at:    datetime


class RollbackRequest(BaseModel):
    to_version: int
    reason:     Optional[str] = None


class RollbackOut(BaseModel):
    rollback_id:    str
    agent_id:       str
    from_version:   int
    to_version:     int
    reason:         Optional[str] = None
    rolled_back_at: datetime
    message:        str
