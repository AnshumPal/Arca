"""
test_eval.py
Phase 3 evaluation framework tests — 6 tests covering the eval pipeline end to end.
All tests reuse the same session-scoped event loop as test_endpoints.py.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient

# Reuse the same fixtures from test_endpoints.py via conftest-style import
# The session-scoped fixtures (create_tables, db_session, client) are already
# defined in test_endpoints.py and shared across the test session.

FAKE_RESPONSE = ("Paris is the capital of France.", "[system]: You are Arca...\n[user]: test")

# A longer research-style response to ensure it lands in the ideal range for agent-2
FAKE_RESEARCH_RESPONSE = (
    " ".join(["Neural networks are computational models"] * 30),  # ~150 words — within agent-2 range
    "[system]: You are Arca research agent...\n[user]: explain neural nets",
)


# ─── Test 1: eval runs after chat ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_eval_runs_after_chat(client: AsyncClient) -> None:
    """POST /chat → background eval fires → GET /eval/scores returns a score."""
    with patch("app.agents.intake.call_llm", new_callable=AsyncMock, return_value=FAKE_RESPONSE):
        resp = await client.post("/chat", json={"message": "hello eval test"})
    assert resp.status_code == 200
    trace_id = resp.json()["trace_id"]

    # Give background task time to run
    await asyncio.sleep(0.3)

    scores_resp = await client.get("/eval/scores")
    assert scores_resp.status_code == 200
    scores = scores_resp.json()
    trace_ids = [s["trace_id"] for s in scores]
    assert trace_id in trace_ids, "Eval score should exist for the trace we just created"


# ─── Test 2: all 4 dimensions present ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_eval_all_4_dimensions_present(client: AsyncClient) -> None:
    """Every evaluated trace must have exactly the 4 dimensions."""
    with patch("app.agents.intake.call_llm", new_callable=AsyncMock, return_value=FAKE_RESPONSE):
        resp = await client.post("/chat", json={"message": "check dimensions please"})
    assert resp.status_code == 200
    trace_id = resp.json()["trace_id"]

    await asyncio.sleep(0.3)

    scores_resp = await client.get("/eval/scores")
    assert scores_resp.status_code == 200

    target = next((s for s in scores_resp.json() if s["trace_id"] == trace_id), None)
    assert target is not None, "Eval score for this trace not found"

    dimension_names = {d["dimension"] for d in target["dimensions"]}
    assert dimension_names == {"latency", "length", "feedback", "error"}


# ─── Test 3: all scores between 0 and 1 ───────────────────────────────────────

@pytest.mark.asyncio
async def test_eval_scores_between_0_and_1(client: AsyncClient) -> None:
    """All individual dimension scores must be in [0.0, 1.0]."""
    # Post a few messages to build up eval data
    for msg in ["hello again", "hi there", "how are you"]:
        with patch("app.agents.intake.call_llm", new_callable=AsyncMock, return_value=FAKE_RESPONSE):
            await client.post("/chat", json={"message": msg})

    await asyncio.sleep(0.5)

    scores_resp = await client.get("/eval/scores", params={"limit": 50})
    assert scores_resp.status_code == 200

    for entry in scores_resp.json():
        assert 0.0 <= entry["overall_score"] <= 1.0, (
            f"overall_score {entry['overall_score']} out of range"
        )
        for dim in entry["dimensions"]:
            assert 0.0 <= dim["score"] <= 1.0, (
                f"Dimension {dim['dimension']} score {dim['score']} out of range"
            )


# ─── Test 4: eval report has all 3 agents ─────────────────────────────────────

@pytest.mark.asyncio
async def test_eval_report_has_all_agents(client: AsyncClient) -> None:
    """GET /eval/report must have entries for all 3 agents."""
    # Ensure each agent gets at least one eval
    with patch("app.agents.intake.call_llm", new_callable=AsyncMock, return_value=FAKE_RESPONSE):
        await client.post("/chat", json={"message": "hello"})  # → agent-1

    with patch("app.agents.research.call_llm", new_callable=AsyncMock, return_value=FAKE_RESPONSE):
        await client.post("/chat", json={"message": "explain how transformers work"})  # → agent-2

    with patch("app.agents.action.call_llm", new_callable=AsyncMock, return_value=FAKE_RESPONSE):
        await client.post("/chat", json={"message": "write a poem about the sea"})  # → agent-3

    await asyncio.sleep(0.5)

    report_resp = await client.get("/eval/report")
    assert report_resp.status_code == 200
    data = report_resp.json()

    assert "generated_at" in data
    assert "total_evaluated" in data
    assert "agents" in data

    agent_ids = {a["agent_id"] for a in data["agents"]}
    assert "agent-1" in agent_ids
    assert "agent-2" in agent_ids
    assert "agent-3" in agent_ids

    for agent in data["agents"]:
        assert "overall_avg" in agent
        assert "traces_evaluated" in agent
        assert "dimensions" in agent
        dims = agent["dimensions"]
        assert all(k in dims for k in ["latency", "length", "feedback", "error"])


# ─── Test 5: compare returns winner ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_eval_compare_returns_winner(client: AsyncClient) -> None:
    """GET /eval/compare must return a valid winner and correct deltas."""
    compare_resp = await client.get(
        "/eval/compare", params={"agent_a": "agent-1", "agent_b": "agent-2"}
    )
    assert compare_resp.status_code == 200
    data = compare_resp.json()

    assert data["agent_a"] == "agent-1"
    assert data["agent_b"] == "agent-2"
    assert data["winner"] in {"agent-1", "agent-2", "tied"}

    assert "comparison" in data
    for dim in ["overall", "latency", "length", "feedback", "error"]:
        assert dim in data["comparison"]
        entry = data["comparison"][dim]
        assert "agent_a" in entry
        assert "agent_b" in entry
        # Delta should equal agent_a - agent_b (within float rounding)
        assert abs(entry["delta"] - (entry["agent_a"] - entry["agent_b"])) < 0.001


# ─── Test 6: POST /eval/run pending ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_post_eval_run_pending(client: AsyncClient) -> None:
    """POST /eval/run with no body evaluates all pending traces."""
    # Trigger pending eval
    run_resp = await client.post("/eval/run", json={})
    assert run_resp.status_code == 200
    data = run_resp.json()
    assert "evaluated" in data
    assert "message" in data
    assert data["evaluated"] >= 0

    # Now POST /eval/run with a known trace_id
    with patch("app.agents.intake.call_llm", new_callable=AsyncMock, return_value=FAKE_RESPONSE):
        chat_resp = await client.post("/chat", json={"message": "run eval on me"})
    assert chat_resp.status_code == 200
    trace_id = chat_resp.json()["trace_id"]

    # Wait for background eval, then manually re-run to confirm idempotency
    await asyncio.sleep(0.3)
    run_resp2 = await client.post("/eval/run", json={"trace_id": trace_id})
    assert run_resp2.status_code == 200
    data2 = run_resp2.json()
    assert data2["evaluated"] == 1
