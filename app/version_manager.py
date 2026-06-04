"""
version_manager.py
Manages the version history of production agents.
Every agent starts at version 1 (original hardcoded prompt).
Each promotion increments the version and marks the new one as current.
Rollback sets a previous version back to is_current = True.
"""

import logging
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentVersion

logger = logging.getLogger(__name__)


async def get_current_prompt(agent_id: str, db: AsyncSession) -> Optional[str]:
    """
    Returns the current system prompt from agent_versions
    where agent_id matches and is_current = True.
    Returns None if no version exists yet.
    """
    result = await db.execute(
        select(AgentVersion).where(
            AgentVersion.agent_id == agent_id,
            AgentVersion.is_current.is_(True),
        )
    )
    row = result.scalar_one_or_none()
    return row.system_prompt if row else None


async def get_version_history(agent_id: str, db: AsyncSession) -> list[AgentVersion]:
    """Returns all versions for an agent, ordered by version DESC."""
    result = await db.execute(
        select(AgentVersion)
        .where(AgentVersion.agent_id == agent_id)
        .order_by(AgentVersion.version.desc())
    )
    return list(result.scalars().all())


async def record_initial_version(
    agent_id: str,
    original_prompt: str,
    db: AsyncSession,
) -> Optional[AgentVersion]:
    """
    Creates version 1 (original hardcoded prompt) if no versions exist yet.
    Returns the version 1 row, or None if versions already existed.
    """
    existing = await db.execute(
        select(func.count()).select_from(AgentVersion).where(
            AgentVersion.agent_id == agent_id
        )
    )
    if (existing.scalar() or 0) > 0:
        return None

    v1 = AgentVersion(
        agent_id=agent_id,
        version=1,
        system_prompt=original_prompt,
        promoted_from=None,
        is_current=True,
    )
    db.add(v1)
    await db.commit()
    await db.refresh(v1)
    logger.info("Recorded initial version 1 for %s", agent_id)
    return v1


async def create_new_version(
    agent_id: str,
    system_prompt: str,
    promoted_from: str,
    db: AsyncSession,
) -> AgentVersion:
    """
    1. Set all existing versions for this agent to is_current = False
    2. Get current max version number
    3. Insert new version with version = max + 1, is_current = True
    """
    # Unset existing current
    existing = await db.execute(
        select(AgentVersion).where(AgentVersion.agent_id == agent_id)
    )
    for v in existing.scalars().all():
        v.is_current = False

    # Find max version
    max_result = await db.execute(
        select(func.max(AgentVersion.version)).where(AgentVersion.agent_id == agent_id)
    )
    next_version = (max_result.scalar() or 0) + 1

    import uuid as _uuid
    new_version = AgentVersion(
        agent_id=agent_id,
        version=next_version,
        system_prompt=system_prompt,
        promoted_from=_uuid.UUID(promoted_from) if isinstance(promoted_from, str) else promoted_from,
        is_current=True,
    )
    db.add(new_version)
    await db.commit()
    await db.refresh(new_version)
    logger.info("Created %s version %d (promoted_from=%s)", agent_id, next_version, promoted_from)
    return new_version


async def activate_version(
    agent_id: str,
    version: int,
    db: AsyncSession,
) -> AgentVersion:
    """
    Used for rollback.
    Sets the specified version to is_current=True and all others to False.
    """
    existing = await db.execute(
        select(AgentVersion).where(AgentVersion.agent_id == agent_id)
    )
    target: AgentVersion | None = None
    for v in existing.scalars().all():
        if v.version == version:
            target = v
            v.is_current = True
        else:
            v.is_current = False

    if target is None:
        raise ValueError(f"Version {version} not found for agent {agent_id}")

    await db.commit()
    await db.refresh(target)
    logger.info("Activated %s version %d", agent_id, version)
    return target
