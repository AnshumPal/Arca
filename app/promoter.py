"""
promoter.py
Executes promotion and rollback operations.
Only called after human approval — never automatically.
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import version_manager
from app.gate import run_gate, to_dict as gate_to_dict
from app.models import AgentVersion, Promotion, Rollback, SandboxAgent

logger = logging.getLogger(__name__)

# Maps agent_id → hardcoded SYSTEM_PROMPT (used when recording initial v1)
# Imported lazily to avoid circular imports during module load
def _hardcoded_prompts() -> dict[str, str]:
    from app.agents.action import SYSTEM_PROMPT as ACTION
    from app.agents.intake import SYSTEM_PROMPT as INTAKE
    from app.agents.research import SYSTEM_PROMPT as RESEARCH
    return {"agent-1": INTAKE, "agent-2": RESEARCH, "agent-3": ACTION}


class PromoterError(Exception):
    """Base class for promoter errors with HTTP status hint."""
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


async def request_promotion(sandbox_id: str, db: AsyncSession) -> Promotion:
    """
    1. Verify sandbox exists and is active
    2. Block if pending promotion already exists for this sandbox
    3. Run gate
    4. Record initial version (v1) if no version exists yet
    5. Create pending Promotion record
    """
    try:
        sid = uuid.UUID(sandbox_id)
    except ValueError:
        raise PromoterError(f"Invalid sandbox_id: {sandbox_id}", status_code=400)

    # Check sandbox
    result = await db.execute(select(SandboxAgent).where(SandboxAgent.id == sid))
    sandbox = result.scalar_one_or_none()
    if sandbox is None:
        raise PromoterError(f"Sandbox not found: {sandbox_id}", status_code=404)
    if sandbox.status != "active":
        raise PromoterError(
            f"Cannot promote sandbox with status '{sandbox.status}'", status_code=400
        )

    # Check for existing pending promotion
    pending_result = await db.execute(
        select(Promotion).where(
            Promotion.sandbox_id == sid,
            Promotion.status == "pending",
        )
    )
    if pending_result.scalar_one_or_none() is not None:
        raise PromoterError(
            f"Pending promotion already exists for sandbox {sandbox_id}",
            status_code=409,
        )

    # Run gate
    gate_result = await run_gate(sandbox_id, db)

    # Record initial v1 for this agent if none exists
    prompts = _hardcoded_prompts()
    hardcoded = prompts.get(sandbox.production_agent_id, "")
    await version_manager.record_initial_version(
        sandbox.production_agent_id, hardcoded, db
    )

    # Create pending promotion record
    promotion = Promotion(
        sandbox_id=sid,
        agent_id=sandbox.production_agent_id,
        status="pending",
        gate_passed=gate_result.passed,
        gate_results=gate_to_dict(gate_result),
    )
    db.add(promotion)
    await db.commit()
    await db.refresh(promotion)

    logger.info(
        "Promotion requested: sandbox=%s agent=%s gate_passed=%s",
        sandbox_id, sandbox.production_agent_id, gate_result.passed,
    )
    return promotion


async def approve_promotion(promotion_id: str, db: AsyncSession) -> Promotion:
    """
    Human approves promotion:
    1. Fetch promotion — must be pending
    2. Get proposed prompt from sandbox.config['system_prompt']
    3. Create new agent version → marks new prompt as current
    4. Suspend the sandbox
    5. Update promotion status
    """
    try:
        pid = uuid.UUID(promotion_id)
    except ValueError:
        raise PromoterError(f"Invalid promotion_id: {promotion_id}", status_code=400)

    result = await db.execute(select(Promotion).where(Promotion.id == pid))
    promotion = result.scalar_one_or_none()
    if promotion is None:
        raise PromoterError(f"Promotion not found: {promotion_id}", status_code=404)
    if promotion.status != "pending":
        raise PromoterError(
            f"Promotion already decided (status: {promotion.status})", status_code=400
        )

    # Get sandbox config
    sb_result = await db.execute(
        select(SandboxAgent).where(SandboxAgent.id == promotion.sandbox_id)
    )
    sandbox = sb_result.scalar_one_or_none()
    if sandbox is None:
        raise PromoterError("Sandbox vanished — cannot approve", status_code=500)

    proposed_prompt = (sandbox.config or {}).get("system_prompt")
    if not proposed_prompt:
        raise PromoterError(
            "Sandbox has no system_prompt in config — nothing to promote",
            status_code=400,
        )

    # Create new version (marks as current)
    new_version = await version_manager.create_new_version(
        agent_id=promotion.agent_id,
        system_prompt=proposed_prompt,
        promoted_from=str(sandbox.id),
        db=db,
    )

    # Suspend the sandbox — its job is done
    sandbox.status = "suspended"

    # Update promotion
    promotion.status          = "approved"
    promotion.decided_at      = datetime.now(timezone.utc)
    promotion.decided_by      = "human"
    promotion.version_created = new_version.version

    await db.commit()
    await db.refresh(promotion)

    # Invalidate prompt cache so live agents pick up new version immediately
    from app.agents.base import invalidate_prompt_cache
    invalidate_prompt_cache(promotion.agent_id)

    logger.info(
        "Promotion approved: %s → %s v%d",
        promotion_id, promotion.agent_id, new_version.version,
    )
    return promotion


async def reject_promotion(promotion_id: str, reason: str, db: AsyncSession) -> Promotion:
    """Mark promotion rejected. Sandbox stays active for more data."""
    try:
        pid = uuid.UUID(promotion_id)
    except ValueError:
        raise PromoterError(f"Invalid promotion_id: {promotion_id}", status_code=400)

    result = await db.execute(select(Promotion).where(Promotion.id == pid))
    promotion = result.scalar_one_or_none()
    if promotion is None:
        raise PromoterError(f"Promotion not found: {promotion_id}", status_code=404)
    if promotion.status != "pending":
        raise PromoterError(
            f"Promotion already decided (status: {promotion.status})", status_code=400
        )

    promotion.status           = "rejected"
    promotion.decided_at       = datetime.now(timezone.utc)
    promotion.decided_by       = "human"
    promotion.rejection_reason = reason

    await db.commit()
    await db.refresh(promotion)
    logger.info("Promotion rejected: %s (reason: %s)", promotion_id, reason)
    return promotion


async def execute_rollback(
    agent_id: str,
    to_version: int,
    reason: str | None,
    db: AsyncSession,
) -> Rollback:
    """
    1. Get current version for agent
    2. Verify to_version exists
    3. Verify to_version != current
    4. Activate target version
    5. Record rollback event
    """
    # Find current version
    current_result = await db.execute(
        select(AgentVersion).where(
            AgentVersion.agent_id == agent_id,
            AgentVersion.is_current.is_(True),
        )
    )
    current = current_result.scalar_one_or_none()
    if current is None:
        raise PromoterError(
            f"No current version exists for {agent_id} — nothing to roll back from",
            status_code=400,
        )

    if current.version == to_version:
        raise PromoterError(
            f"Already on version {to_version} — nothing to roll back to",
            status_code=400,
        )

    # Verify target exists
    target_result = await db.execute(
        select(AgentVersion).where(
            AgentVersion.agent_id == agent_id,
            AgentVersion.version == to_version,
        )
    )
    target = target_result.scalar_one_or_none()
    if target is None:
        raise PromoterError(
            f"Version {to_version} not found for {agent_id}", status_code=404
        )

    # Activate target version
    await version_manager.activate_version(agent_id, to_version, db)

    # Record rollback
    rollback = Rollback(
        agent_id=agent_id,
        from_version=current.version,
        to_version=to_version,
        reason=reason,
    )
    db.add(rollback)
    await db.commit()
    await db.refresh(rollback)

    # Invalidate prompt cache
    from app.agents.base import invalidate_prompt_cache
    invalidate_prompt_cache(agent_id)

    logger.info(
        "Rollback executed: %s v%d → v%d (%s)",
        agent_id, current.version, to_version, reason,
    )
    return rollback
