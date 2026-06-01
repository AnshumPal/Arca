"""
test_sandbox.py
Phase 4 sandbox tests — 7 tests covering creation, shadow execution, and comparison.
All tests share the session-scoped fixtures from conftest.py.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

FAKE_LLM = ("Sandbox response text for testing purposes.", "[system]: ...\n[user]: test")

SANDBOX_CONFIG = {
    "system_prompt": "You are an experimental research agent with extra detail.",
    "model": "gpt-4o-mini",
    "temperature": 0.5,
}


# ─── Test 1: create sandbox success ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_sandbox_success(client: AsyncClient) -> None:
    """POST /sandbox with valid data → 200 + sandbox_id + status active."""
    resp = await client.post(
        "/sandbox",
        json={
            "name": "test-research-sandbox-v1",
            "production_agent_id": "agent-2",
            "config": SANDBOX_CONFIG,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "sandbox_id" in data
    assert data["status"] == "active"
    assert data["production_agent_id"] == "agent-2"
    assert data["name"] == "test-research-sandbox-v1"


# ─── Test 2: invalid production agent ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_sandbox_invalid_agent(client: AsyncClient) -> None:
    """POST /sandbox with unknown production_agent_id → 400."""
    resp = await client.post(
        "/sandbox",
        json={
            "name": "invalid-agent-sandbox",
            "production_agent_id": "agent-99",
            "config": {},
        },
    )
    assert resp.status_code == 400


# ─── Test 3: duplicate name returns 409 ───────────────────────────────────────

@pytest.mark.asyncio
async def test_create_sandbox_duplicate_name(client: AsyncClient) -> None:
    """POST /sandbox twice with same name → second returns 409."""
    payload = {
        "name": "duplicate-sandbox-name",
        "production_agent_id": "agent-1",
        "config": {},
    }
    first = await client.post("/sandbox", json=payload)
    assert first.status_code == 200

    second = await client.post("/sandbox", json=payload)
    assert second.status_code == 409


# ─── Test 4: shadow execution creates sandbox trace ───────────────────────────

@pytest.mark.asyncio
async def test_shadow_execution_creates_sandbox_trace(client: AsyncClient) -> None:
    """POST /chat → background shadow runs → GET /sandbox/{id} shows trace_count >= 1."""
    # Create sandbox for agent-1
    create_resp = await client.post(
        "/sandbox",
        json={
            "name": "shadow-test-intake-sandbox",
            "production_agent_id": "agent-1",
            "config": {"system_prompt": "You are a shadow intake agent."},
        },
    )
    assert create_resp.status_code == 200
    sandbox_id = create_resp.json()["sandbox_id"]

    # Send a chat that routes to agent-1
    with patch("app.agents.intake.call_llm", new_callable=AsyncMock, return_value=FAKE_LLM):
        with patch("app.sandbox.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                return_value=AsyncMock(
                    choices=[AsyncMock(message=AsyncMock(content="Shadow response"))]
                )
            )
            mock_get_client.return_value = mock_client
            chat_resp = await client.post(
                "/chat",
                json={"message": "hello shadow test", "session_id": "shadow-sess"},
            )
    assert chat_resp.status_code == 200

    # Wait for background shadow task
    await asyncio.sleep(0.5)

    detail_resp = await client.get(f"/sandbox/{sandbox_id}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["trace_count"] >= 1


# ─── Test 5: list filters by status ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_sandbox_list_filters_by_status(client: AsyncClient) -> None:
    """Create sandbox, suspend it → active list excludes it, suspended list includes it."""
    create_resp = await client.post(
        "/sandbox",
        json={
            "name": "filter-status-test-sandbox",
            "production_agent_id": "agent-3",
            "config": {},
        },
    )
    assert create_resp.status_code == 200
    sandbox_id = create_resp.json()["sandbox_id"]

    # Suspend it
    del_resp = await client.delete(f"/sandbox/{sandbox_id}?action=suspend")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "suspended"

    # Should NOT appear in active list
    active_resp = await client.get("/sandbox?status=active")
    assert active_resp.status_code == 200
    active_ids = [s["sandbox_id"] for s in active_resp.json()]
    assert sandbox_id not in active_ids

    # SHOULD appear in suspended list
    susp_resp = await client.get("/sandbox?status=suspended")
    assert susp_resp.status_code == 200
    susp_ids = [s["sandbox_id"] for s in susp_resp.json()]
    assert sandbox_id in susp_ids


# ─── Test 6: compare returns insufficient_data ────────────────────────────────

@pytest.mark.asyncio
async def test_sandbox_compare_insufficient_data(client: AsyncClient) -> None:
    """New sandbox with 0 traces → /compare returns verdict insufficient_data."""
    create_resp = await client.post(
        "/sandbox",
        json={
            "name": "compare-insufficient-sandbox",
            "production_agent_id": "agent-2",
            "config": {},
        },
    )
    assert create_resp.status_code == 200
    sandbox_id = create_resp.json()["sandbox_id"]

    compare_resp = await client.get(f"/sandbox/{sandbox_id}/compare")
    assert compare_resp.status_code == 200
    data = compare_resp.json()
    assert data["verdict"] == "insufficient_data"
    assert data["min_traces_required"] == 10
    assert data["sandbox_trace_count"] == 0


# ─── Test 7: soft delete ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sandbox_soft_delete(client: AsyncClient) -> None:
    """DELETE /sandbox/{id}?action=delete → status deleted, not in active list."""
    create_resp = await client.post(
        "/sandbox",
        json={
            "name": "soft-delete-test-sandbox",
            "production_agent_id": "agent-1",
            "config": {},
        },
    )
    assert create_resp.status_code == 200
    sandbox_id = create_resp.json()["sandbox_id"]

    # Soft delete
    del_resp = await client.delete(f"/sandbox/{sandbox_id}?action=delete")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deleted"

    # Detail endpoint still returns it (data retained)
    detail_resp = await client.get(f"/sandbox/{sandbox_id}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["status"] == "deleted"

    # Not in active list
    active_resp = await client.get("/sandbox?status=active")
    active_ids = [s["sandbox_id"] for s in active_resp.json()]
    assert sandbox_id not in active_ids
