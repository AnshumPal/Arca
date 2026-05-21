"""
conftest.py
Shared fixtures for all test modules.
Session-scoped so the whole test run shares one event loop + one DB connection.

URL priority:
  1. TEST_DATABASE_URL env var  (explicit override — used in CI)
  2. postgresql+asyncpg://arca:arca@localhost:5432/arca  (local Docker default)

Do NOT fall back to settings.async_database_url here — that points to the
production Neon database and drop_all at teardown would wipe production tables.
"""

import os
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.eval_runner as eval_runner_module
from app.database import Base, get_db
from app.main import app

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://arca:arca@localhost:5432/arca",
)

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)

# Redirect background eval tasks to the test database so they can find
# traces written by the test session (instead of connecting to production Neon).
eval_runner_module.AsyncSessionLocal = TestSessionLocal


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def create_tables() -> AsyncGenerator[None, None]:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
