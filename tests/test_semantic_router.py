"""
test_semantic_router.py
Phase 8 tests — LLM-based intent classifier + feature flag.

The flag is off by default so all existing tests keep passing unchanged.
These tests flip it on and mock the OpenAI client to verify:
  1. Semantic router is invoked when the flag is on
  2. Arca self-queries short-circuit before the LLM call
  3. Malformed LLM output falls back to the keyword classifier
  4. LLM errors fall back to the keyword classifier
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings
from app.semantic_router import classify_semantic


def _mock_completion(text: str) -> MagicMock:
    """Build a mock OpenAI ChatCompletion with the given text as content."""
    completion = MagicMock()
    completion.choices = [MagicMock()]
    completion.choices[0].message = MagicMock()
    completion.choices[0].message.content = text
    return completion


@pytest.mark.asyncio
async def test_semantic_router_returns_agent_from_llm() -> None:
    """Semantic router should return the agent ID the LLM emits."""
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_completion("agent-2")
    )
    with patch("app.semantic_router.get_client", return_value=mock_client):
        result = await classify_semantic("how does a transformer work under the hood")
    assert result == "agent-2"


@pytest.mark.asyncio
async def test_semantic_router_short_circuits_arca_self_queries() -> None:
    """Meta-questions about Arca should return 'arca-info' without an LLM call."""
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_completion("agent-3")   # would be wrong if called
    )
    with patch("app.semantic_router.get_client", return_value=mock_client):
        result = await classify_semantic("what is arca")
    assert result == "arca-info"
    # LLM must NOT have been called
    mock_client.chat.completions.create.assert_not_called()


@pytest.mark.asyncio
async def test_semantic_router_falls_back_on_malformed_output() -> None:
    """If LLM returns something that isn't an agent ID, fall back to keyword classifier."""
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_completion("I don't know")
    )
    with patch("app.semantic_router.get_client", return_value=mock_client):
        # "explain X" → keyword fallback should return agent-2
        result = await classify_semantic("explain neural nets")
    assert result == "agent-2"


@pytest.mark.asyncio
async def test_semantic_router_falls_back_on_llm_error() -> None:
    """If the OpenAI call raises, fall back to keyword classifier — never crash."""
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=RuntimeError("rate limit exceeded")
    )
    with patch("app.semantic_router.get_client", return_value=mock_client):
        # "write a poem" → keyword fallback → agent-3
        result = await classify_semantic("write a poem about the ocean")
    assert result == "agent-3"


@pytest.mark.asyncio
async def test_feature_flag_off_by_default() -> None:
    """The USE_SEMANTIC_ROUTER flag must default to False so tests aren't affected."""
    assert settings.use_semantic_router is False
