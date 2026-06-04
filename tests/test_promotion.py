"""
test_promotion.py
Phase 6 promotion gate + rollback tests — 8 tests.
All tests share the session-scoped fixtures from conftest.py.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SandboxAgent, SandboxEvalScore, SandboxTrace


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _seed_passing_sandbox(
    db: AsyncSession,
    name: str,
    agent_id: str = "agent-1",
    trace_count: int = 15,
    overall: float = 0.95,
    error_score: float = 0.95,
    latency_score: float = 0.95,
    system_prompt: str = "You are the improved agent.",
) -> str:
    """Create a sandbox + N traces + per-dimension scores that should pass the gate."""
    sandbox = SandboxAgent(
        name=name,
        production_agent_id=agent_id,
        status="active",
        config={"system_prompt": system_prompt, "model": "gpt-4o-mini"},
    )
    db.add(sandbox)
    await db.flush()

    for _ in range(trace_count):
        trace = SandboxTrace(
            sandbox_id=sandbox.id,
            production_agent_id=agent_id,
            input="some test input",
            output="some test output",
            latency_ms=500,
        )
        db.add(trace)
        await db.flush()
        for dim, score in (
            ("latency",  latency_score),
            ("length",   0.9),
            ("feedback", 0.5),
            ("error",    error_score),
        ):
            db.add(SandboxEvalScore(
                sandbox_id=sandbox.id,
                sandbox_trace_id=trace.id,
                dimension=dim,
                score=score,
                reasoning="seed",
                overall_score=overall,
            ))

    await db.commit()
    return str(sandbox.id)


async def _create_empty_sandbox(
    db: AsyncSession, name: str, agent_id: str = "agent-1"
) -> str:
    sandbox = SandboxAgent(
        name=name,
        production_agent_id=agent_id,
        status="active",
        config={"system_prompt": "Empty test prompt."},
    )
    db.add(sandbox)
    await db.commit()
    await db.refresh(sandbox)
    return str(sandbox.id)


# ─── Test 1: gate runs and returns 4 checks ───────────────────────────────────

@pytest.mark.asyncio
async def test_request_promotion_runs_gate(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    sid = await _seed_passing_sandbox(
        db_session, name=f"gate-runs-{uuid.uuid4().hex[:8]}", agent_id="agent-1"
    )
    resp = await client.post(f"/promote/{sid}")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "promotion_id" in data
    assert data["status"] == "pending"
    assert len(data["gate_results"]["checks"]) == 4


# ─── Test 2: gate fails on 0 traces ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_gate_fails_on_insufficient_traces(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    sid = await _create_empty_sandbox(db_session, name=f"empty-{uuid.uuid4().hex[:8]}")
    resp = await client.post(f"/promote/{sid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["gate_passed"] is False
    min_traces_check = next(c for c in data["gate_results"]["checks"] if c["name"] == "min_traces")
    assert min_traces_check["passed"] is False


# ─── Test 3: approve creates v2 and marks current ────────────────────────────

@pytest.mark.asyncio
async def test_approve_promotion_updates_agent_prompt(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    sid = await _seed_passing_sandbox(
        db_session,
        name=f"approve-{uuid.uuid4().hex[:8]}",
        agent_id="agent-2",
        system_prompt="You are the improved research agent.",
    )
    promo_resp = await client.post(f"/promote/{sid}")
    assert promo_resp.status_code == 200
    pid = promo_resp.json()["promotion_id"]

    approve_resp = await client.post(f"/promote/{pid}/approve")
    assert approve_resp.status_code == 200
    assert approve_resp.json()["version_created"] >= 2

    versions_resp = await client.get("/agents/agent-2/versions")
    assert versions_resp.status_code == 200
    versions = versions_resp.json()
    current = next((v for v in versions if v["is_current"]), None)
    assert current is not None
    assert current["system_prompt"] == "You are the improved research agent."


# ─── Test 4: live prompt changes after approval (via cache invalidation) ─────

@pytest.mark.asyncio
async def test_live_prompt_changes_after_approval(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Pre-load cache with hardcoded prompt
    from app.agents.base import _prompt_cache, get_live_prompt, invalidate_prompt_cache
    invalidate_prompt_cache("agent-3")

    hardcoded = "You are the original action agent."
    _ = await get_live_prompt("agent-3", hardcoded)
    assert "agent-3" in _prompt_cache

    sid = await _seed_passing_sandbox(
        db_session,
        name=f"live-prompt-{uuid.uuid4().hex[:8]}",
        agent_id="agent-3",
        system_prompt="You are the improved action agent — version 2.",
    )
    promo_resp = await client.post(f"/promote/{sid}")
    pid = promo_resp.json()["promotion_id"]
    approve_resp = await client.post(f"/promote/{pid}/approve")
    assert approve_resp.status_code == 200

    # Cache should have been invalidated by approve_promotion
    assert "agent-3" not in _prompt_cache

    new_prompt = await get_live_prompt("agent-3", hardcoded)
    assert new_prompt == "You are the improved action agent — version 2."


# ─── Test 5: reject keeps sandbox active ──────────────────────────────────────

@pytest.mark.asyncio
async def test_reject_promotion_keeps_sandbox_active(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    sid = await _seed_passing_sandbox(
        db_session, name=f"reject-{uuid.uuid4().hex[:8]}", agent_id="agent-1"
    )
    promo_resp = await client.post(f"/promote/{sid}")
    pid = promo_resp.json()["promotion_id"]

    reject_resp = await client.post(
        f"/promote/{pid}/reject",
        json={"reason": "Not enough data quality yet"},
    )
    assert reject_resp.status_code == 200
    assert reject_resp.json()["status"] == "rejected"

    detail_resp = await client.get(f"/sandbox/{sid}")
    assert detail_resp.json()["status"] == "active"


# ─── Test 6: cannot approve already-decided promotion ─────────────────────────

@pytest.mark.asyncio
async def test_cannot_approve_already_decided_promotion(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    sid = await _seed_passing_sandbox(
        db_session, name=f"twice-{uuid.uuid4().hex[:8]}", agent_id="agent-1"
    )
    promo_resp = await client.post(f"/promote/{sid}")
    pid = promo_resp.json()["promotion_id"]

    first = await client.post(f"/promote/{pid}/approve")
    assert first.status_code == 200

    second = await client.post(f"/promote/{pid}/approve")
    assert second.status_code == 400


# ─── Test 7: rollback restores previous version ───────────────────────────────

@pytest.mark.asyncio
async def test_rollback_restores_previous_version(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Approve a promotion to get v2 for agent-2 (may already exist from test 3)
    sid = await _seed_passing_sandbox(
        db_session,
        name=f"rollback-{uuid.uuid4().hex[:8]}",
        agent_id="agent-2",
        system_prompt="Improved research v-rollback test.",
    )
    promo_resp = await client.post(f"/promote/{sid}")
    pid = promo_resp.json()["promotion_id"]
    approve_resp = await client.post(f"/promote/{pid}/approve")
    assert approve_resp.status_code == 200
    new_version = approve_resp.json()["version_created"]

    # Roll back to v1
    rb_resp = await client.post(
        "/agents/agent-2/rollback",
        json={"to_version": 1, "reason": "Latency regression observed"},
    )
    assert rb_resp.status_code == 200
    assert rb_resp.json()["from_version"] == new_version
    assert rb_resp.json()["to_version"] == 1

    versions_resp = await client.get("/agents/agent-2/versions")
    versions = versions_resp.json()
    current = next(v for v in versions if v["is_current"])
    assert current["version"] == 1

    rollbacks_resp = await client.get("/rollbacks?agent_id=agent-2")
    assert rollbacks_resp.status_code == 200
    assert len(rollbacks_resp.json()) >= 1


# ─── Test 8: duplicate pending promotion blocked ──────────────────────────────

@pytest.mark.asyncio
async def test_duplicate_promotion_request_blocked(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    sid = await _seed_passing_sandbox(
        db_session, name=f"dup-{uuid.uuid4().hex[:8]}", agent_id="agent-1"
    )
    first = await client.post(f"/promote/{sid}")
    assert first.status_code == 200

    second = await client.post(f"/promote/{sid}")
    assert second.status_code == 409
