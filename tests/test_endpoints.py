import os
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    os.environ.get("DATABASE_URL", "postgresql+asyncpg://arca:arca@localhost:5432/arca"),
)

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)

FAKE_RESPONSE = ("Paris is the capital of France.", "[system]: You are Arca...\n[user]: test")


# scope="session" + loop_scope="session" → one event loop for the whole test run.
# This prevents asyncpg's "Future attached to a different loop" error that occurs
# when function-scoped tests spawn their own loops but the engine pool was created
# on the session loop.
@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def create_tables() -> AsyncGenerator[None, None]:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(loop_scope="session")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture(loop_scope="session")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_chat_returns_response(client: AsyncClient) -> None:
    with patch("app.agent.run", new_callable=AsyncMock, return_value=FAKE_RESPONSE):
        resp = await client.post("/chat", json={"message": "What is the capital of France?"})
    assert resp.status_code == 200
    data = resp.json()
    assert "response" in data
    assert "trace_id" in data
    assert "latency_ms" in data
    assert data["response"] == FAKE_RESPONSE[0]


@pytest.mark.asyncio
async def test_chat_logs_trace(client: AsyncClient) -> None:
    with patch("app.agent.run", new_callable=AsyncMock, return_value=FAKE_RESPONSE):
        chat_resp = await client.post(
            "/chat",
            json={"message": "Trace log test", "session_id": "sess-trace-test"},
        )
    assert chat_resp.status_code == 200
    trace_id = chat_resp.json()["trace_id"]

    traces_resp = await client.get("/traces", params={"session_id": "sess-trace-test"})
    assert traces_resp.status_code == 200
    trace_ids = [t["id"] for t in traces_resp.json()]
    assert trace_id in trace_ids


@pytest.mark.asyncio
async def test_feedback_updates_trace(client: AsyncClient) -> None:
    with patch("app.agent.run", new_callable=AsyncMock, return_value=FAKE_RESPONSE):
        chat_resp = await client.post(
            "/chat",
            json={"message": "Feedback test", "session_id": "sess-fb-test"},
        )
    assert chat_resp.status_code == 200
    trace_id = chat_resp.json()["trace_id"]

    fb_resp = await client.post("/feedback", json={"trace_id": trace_id, "feedback": 1})
    assert fb_resp.status_code == 200
    assert fb_resp.json() == {"status": "ok"}

    traces_resp = await client.get("/traces", params={"session_id": "sess-fb-test"})
    traces = traces_resp.json()
    target = next((t for t in traces if t["id"] == trace_id), None)
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
