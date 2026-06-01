"""
optimizer.py
Orchestrates the full optimize cycle:
  1. Analyze all agents for failure patterns
  2. For each failure pattern — propose an improved prompt
  3. For each proposal — create a sandbox to test it
  4. Write the full run record to optimizer_runs

Does NOT promote anything to production — that is Phase 6.
Never leaves a run in 'running' state.
"""

import dataclasses
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.action import SYSTEM_PROMPT as ACTION_PROMPT
from app.agents.intake import SYSTEM_PROMPT as INTAKE_PROMPT
from app.agents.research import SYSTEM_PROMPT as RESEARCH_PROMPT
from app.analyzer import FailurePattern, analyze_all_agents
from app.models import OptimizerRun, SandboxAgent
from app.proposer import OptimizationProposal, propose_improvement
from app.sandbox import create_sandbox

logger = logging.getLogger(__name__)

# Current production system prompts — used to build improvement proposals
_AGENT_PROMPTS: dict[str, str] = {
    "agent-1": INTAKE_PROMPT,
    "agent-2": RESEARCH_PROMPT,
    "agent-3": ACTION_PROMPT,
}


def _pattern_to_dict(p: FailurePattern) -> dict:
    return dataclasses.asdict(p)


def _proposal_to_dict(p: OptimizationProposal) -> dict:
    return dataclasses.asdict(p)


async def run_optimizer_cycle(
    db: AsyncSession,
    triggered_by: str = "schedule",
) -> OptimizerRun:
    """
    Full optimizer cycle. Analyzes → proposes → creates sandboxes.
    Always completes or fails — never stays 'running'.
    """
    # Step 1: create run record
    run = OptimizerRun(
        status="running",
        triggered_by=triggered_by,
        agents_analyzed=[],
        findings=[],
        proposals=[],
        sandboxes_created=[],
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    logger.info("Optimizer run started: %s (triggered_by=%s)", run.id, triggered_by)

    try:
        # Step 2: analyze all agents
        patterns: list[FailurePattern] = await analyze_all_agents(db, lookback_days=7)
        agents_analyzed = list(dict.fromkeys(p.agent_id for p in patterns)) or list(
            ["agent-1", "agent-2", "agent-3"]
        )

        if not patterns:
            logger.info("Optimizer: no failure patterns found — all agents healthy")
            run.status          = "completed"
            run.agents_analyzed = agents_analyzed
            run.findings        = []
            run.proposals       = []
            run.sandboxes_created = []
            run.completed_at    = datetime.now(timezone.utc)
            await db.commit()
            await db.refresh(run)
            return run

        # Step 3: propose improvements
        proposals: list[OptimizationProposal] = []
        for pattern in patterns:
            current_prompt = _AGENT_PROMPTS.get(pattern.agent_id, "You are a helpful assistant.")
            try:
                proposal = await propose_improvement(pattern, current_prompt, db)
                proposals.append(proposal)
            except Exception as exc:
                logger.error(
                    "Proposer failed for %s/%s: %s",
                    pattern.agent_id, pattern.dimension, exc,
                )
                raise  # re-raise so run is marked failed

        # Step 4: create sandboxes for each proposal
        sandbox_ids: list[str] = []
        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")

        for proposal in proposals:
            sandbox_name = f"{proposal.agent_id}-opt-{proposal.dimension}-{ts}"

            # Skip if an active sandbox with this name already exists
            existing = await db.execute(
                select(SandboxAgent).where(
                    SandboxAgent.name == sandbox_name,
                    SandboxAgent.status == "active",
                )
            )
            if existing.scalar_one_or_none() is not None:
                logger.info("Optimizer: sandbox '%s' already active — skipping", sandbox_name)
                continue

            try:
                sandbox = await create_sandbox(
                    name=sandbox_name,
                    production_agent_id=proposal.agent_id,
                    config=proposal.sandbox_config,
                    db=db,
                )
                sandbox_ids.append(str(sandbox.id))
                logger.info("Optimizer: created sandbox %s → %s", sandbox_name, sandbox.id)
            except Exception as exc:
                logger.error("Optimizer: failed to create sandbox '%s': %s", sandbox_name, exc)

        # Step 5: mark run completed
        run.status           = "completed"
        run.agents_analyzed  = agents_analyzed
        run.findings         = [_pattern_to_dict(p) for p in patterns]
        run.proposals        = [_proposal_to_dict(p) for p in proposals]
        run.sandboxes_created = sandbox_ids
        run.completed_at     = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(run)

        logger.info(
            "Optimizer run completed: %s | findings=%d proposals=%d sandboxes=%d",
            run.id, len(patterns), len(proposals), len(sandbox_ids),
        )
        return run

    except Exception as exc:
        logger.error("Optimizer run %s failed: %s", run.id, exc)
        run.status       = "failed"
        run.error        = str(exc)
        run.completed_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(run)
        return run
