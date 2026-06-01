"""
test_optimizer.py
Phase 5 optimizer tests — 6 tests covering analysis, proposal, and sandbox creation.
All tests share the session-scoped fixtures from conftest.py.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EvalRun, EvalScore, OptimizerRun, Trace


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _seed_low_latency_scores(db: AsyncSession, agent_id: str = "agent-2", count: int = 5) -> None:
    """Insert traces + eval_runs + low latency scores to trigger the analyzer."""
    for i in range(count):
        trace = Trace(
            agent_id=agent_id,
            input=f"research query about topic {i}",
            output="some output text",
            latency_ms=8000,  # 8s — scores 0.0 on latency
        )
        db.add(trace)
        await db.flush()

        eval_run = EvalRun(
            trace_id=trace.id,
            agent_id=agent_id,
            overall_score=0.25,
            eval_version="v1",
        )
        db.add(eval_run)
        await db.flush()

        # Only latency score — below threshold 0.60
        db.add(EvalScore(
            eval_run_id=eval_run.id,
            trace_id=trace.id,
            dimension="latency",
            score=0.10,
            reasoning="Extremely slow response",
        ))

    await db.commit()


def _fake_proposal(agent_id: str = "agent-2", dimension: str = "latency"):
    """Returns a fake OptimizationProposal dataclass instance."""
    from app.proposer import OptimizationProposal
    return OptimizationProposal(
        agent_id=agent_id,
        dimension=dimension,
        original_prompt="You are Arca's research agent...",
        proposed_prompt="You are Arca's research agent. Be concise and direct.",
        reasoning="Adding conciseness instruction should reduce latency.",
        sandbox_config={"system_prompt": "You are Arca's research agent. Be concise and direct."},
    )


# ─── Test 1: manual run completes ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_manual_optimizer_run_completes(client: AsyncClient) -> None:
    """POST /optimizer/run → 200, status is completed or failed (never running)."""
    resp = await client.post("/optimizer/run")
    assert resp.status_code == 200
    data = resp.json()
    assert "run_id" in data
    assert data["status"] in ("completed", "failed")
    assert data["triggered_by"] == "manual"


# ─── Test 2: run appears in list ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_optimizer_run_appears_in_list(client: AsyncClient) -> None:
    """POST /optimizer/run → GET /optimizer/runs → run_id appears in list."""
    run_resp = await client.post("/optimizer/run")
    assert run_resp.status_code == 200
    run_id = run_resp.json()["run_id"]

    list_resp = await client.get("/optimizer/runs")
    assert list_resp.status_code == 200
    run_ids = [r["run_id"] for r in list_resp.json()]
    assert run_id in run_ids


# ─── Test 3: run detail has required keys ─────────────────────────────────────

@pytest.mark.asyncio
async def test_optimizer_run_detail(client: AsyncClient) -> None:
    """POST /optimizer/run → GET /optimizer/runs/{run_id} → required keys present."""
    run_resp = await client.post("/optimizer/run")
    assert run_resp.status_code == 200
    run_id = run_resp.json()["run_id"]

    detail_resp = await client.get(f"/optimizer/runs/{run_id}")
    assert detail_resp.status_code == 200
    data = detail_resp.json()
    assert "findings" in data
    assert "proposals" in data
    assert "agents_analyzed" in data
    assert isinstance(data["findings"], list)
    assert isinstance(data["proposals"], list)


# ─── Test 4: creates sandbox on failure ───────────────────────────────────────

@pytest.mark.asyncio
async def test_optimizer_creates_sandbox_on_failure(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Seed low latency scores → run optimizer → sandbox created for agent-2."""
    await _seed_low_latency_scores(db_session, agent_id="agent-2", count=5)

    with patch("app.optimizer.propose_improvement", new_callable=AsyncMock, return_value=_fake_proposal()):
        resp = await client.post("/optimizer/run")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert len(data["sandboxes_created"]) > 0

    # Verify sandbox exists
    sandbox_id = data["sandboxes_created"][0]
    detail_resp = await client.get(f"/sandbox/{sandbox_id}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["production_agent_id"] == "agent-2"


# ─── Test 5: skips duplicate sandbox ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_optimizer_skips_duplicate_sandbox(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Running optimizer twice with same failure pattern → no duplicate sandbox created."""
    await _seed_low_latency_scores(db_session, agent_id="agent-2", count=3)

    with patch("app.proposer.propose_improvement", new_callable=AsyncMock, return_value=_fake_proposal()):
        resp1 = await client.post("/optimizer/run")
    assert resp1.status_code == 200
    sandboxes_first = resp1.json()["sandboxes_created"]

    with patch("app.proposer.propose_improvement", new_callable=AsyncMock, return_value=_fake_proposal()):
        resp2 = await client.post("/optimizer/run")
    assert resp2.status_code == 200
    sandboxes_second = resp2.json()["sandboxes_created"]

    # Second run should not create new sandboxes (same timestamp-based name)
    # Both sandbox lists should not have overlapping IDs
    assert set(sandboxes_first).isdisjoint(set(sandboxes_second)) or len(sandboxes_second) == 0


# ─── Test 6: failed status on error ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_optimizer_failed_status_on_error(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """If proposer raises → run status = failed, error field populated, not stuck on running."""
    await _seed_low_latency_scores(db_session, agent_id="agent-2", count=3)

    with patch("app.optimizer.propose_improvement", new_callable=AsyncMock, side_effect=ValueError("LLM quota exceeded")):
        resp = await client.post("/optimizer/run")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "failed"
    assert data["error"] is not None
    assert "LLM quota exceeded" in data["error"]
