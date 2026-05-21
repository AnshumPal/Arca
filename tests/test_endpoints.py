from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

FAKE_RESPONSE = ("Paris is the capital of France.", "[system]: You are Arca...\n[user]: test")


# ─── Phase 1 tests (unchanged) ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chat_returns_response(client: AsyncClient) -> None:
    with patch("app.agents.intake.call_llm", new_callable=AsyncMock, return_value=FAKE_RESPONSE):
        resp = await client.post("/chat", json={"message": "hello"})
    assert resp.status_code == 200
    data = resp.json()
    assert "response" in data
    assert "trace_id" in data
    assert "latency_ms" in data
    assert "agent_id" in data
    assert data["response"] == FAKE_RESPONSE[0]


@pytest.mark.asyncio
async def test_chat_logs_trace(client: AsyncClient) -> None:
    with patch("app.agents.intake.call_llm", new_callable=AsyncMock, return_value=FAKE_RESPONSE):
        chat_resp = await client.post(
            "/chat",
            json={"message": "hello there", "session_id": "sess-trace-test"},
        )
    assert chat_resp.status_code == 200
    trace_id = chat_resp.json()["trace_id"]

    traces_resp = await client.get("/traces", params={"session_id": "sess-trace-test"})
    assert traces_resp.status_code == 200
    trace_ids = [t["id"] for t in traces_resp.json()]
    assert trace_id in trace_ids


@pytest.mark.asyncio
async def test_feedback_updates_trace(client: AsyncClient) -> None:
    with patch("app.agents.intake.call_llm", new_callable=AsyncMock, return_value=FAKE_RESPONSE):
        chat_resp = await client.post(
            "/chat",
            json={"message": "hello feedback", "session_id": "sess-fb-test"},
        )
    assert chat_resp.status_code == 200
    trace_id = chat_resp.json()["trace_id"]

    fb_resp = await client.post("/feedback", json={"trace_id": trace_id, "feedback": 1})
    assert fb_resp.status_code == 200
    assert fb_resp.json() == {"status": "ok"}

    traces_resp = await client.get("/traces", params={"session_id": "sess-fb-test"})
    target = next((t for t in traces_resp.json() if t["id"] == trace_id), None)
    assert target is not None
    assert target["feedback"] == 1


@pytest.mark.asyncio
async def test_report_structure(client: AsyncClient) -> None:
    resp = await client.get("/report")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_traces" in data
    assert "avg_latency_ms" in data
    assert "error_count" in data
    assert "feedback" in data
    fb = data["feedback"]
    assert "positive" in fb
    assert "negative" in fb
    assert "none" in fb


# ─── Phase 2 tests ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_routing_to_research_agent(client: AsyncClient) -> None:
    with patch("app.agents.research.call_llm", new_callable=AsyncMock, return_value=FAKE_RESPONSE):
        resp = await client.post(
            "/chat",
            json={"message": "explain how neural networks work", "session_id": "sess-research"},
        )
    assert resp.status_code == 200
    assert resp.json()["agent_id"] == "agent-2"


@pytest.mark.asyncio
async def test_routing_to_action_agent(client: AsyncClient) -> None:
    with patch("app.agents.action.call_llm", new_callable=AsyncMock, return_value=FAKE_RESPONSE):
        resp = await client.post(
            "/chat",
            json={"message": "write a summary of my project", "session_id": "sess-action"},
        )
    assert resp.status_code == 200
    assert resp.json()["agent_id"] == "agent-3"


@pytest.mark.asyncio
async def test_routing_default_to_intake(client: AsyncClient) -> None:
    with patch("app.agents.intake.call_llm", new_callable=AsyncMock, return_value=FAKE_RESPONSE):
        resp = await client.post(
            "/chat",
            json={"message": "hello", "session_id": "sess-intake"},
        )
    assert resp.status_code == 200
    assert resp.json()["agent_id"] == "agent-1"


@pytest.mark.asyncio
async def test_get_agents_returns_three(client: AsyncClient) -> None:
    resp = await client.get("/agents")
    assert resp.status_code == 200
    agents = resp.json()
    assert len(agents) == 3
    for agent in agents:
        assert "agent_id" in agent
        assert "description" in agent


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["agents_active"] == 3


@pytest.mark.asyncio
async def test_chat_response_includes_agent_id(client: AsyncClient) -> None:
    with patch("app.agents.intake.call_llm", new_callable=AsyncMock, return_value=FAKE_RESPONSE):
        resp = await client.post("/chat", json={"message": "hi"})
    assert resp.status_code == 200
    assert "agent_id" in resp.json()
