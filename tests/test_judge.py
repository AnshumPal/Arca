"""
test_judge.py
Phase 9 tests — LLM-as-judge quality dimension.

The flag USE_LLM_JUDGE defaults to False so existing tests remain unaffected.
These tests toggle it on with monkeypatch and mock the OpenAI client to verify:
  1. Judge returns None when the flag is off (no LLM call)
  2. Judge returns None when the trace has no output
  3. Valid JSON response → parsed correctly, score clamped to [0,1]
  4. Malformed JSON → returns None, does NOT crash
  5. LLM raises → returns None, does NOT crash
  6. Feature flag defaults to False
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings
from app.judge import judge_trace


def _mock_completion(text: str) -> MagicMock:
    """Build a mock OpenAI ChatCompletion returning `text`."""
    completion = MagicMock()
    completion.choices = [MagicMock()]
    completion.choices[0].message = MagicMock()
    completion.choices[0].message.content = text
    return completion


def _fake_trace(output: str | None = "some response", input_text: str = "hi") -> SimpleNamespace:
    """Duck-typed trace object with just the fields judge_trace touches."""
    return SimpleNamespace(id="fake-trace-id", input=input_text, output=output)


@pytest.mark.asyncio
async def test_judge_returns_none_when_flag_off(monkeypatch) -> None:
    monkeypatch.setattr(settings, "use_llm_judge", False)
    result = await judge_trace(_fake_trace())
    assert result is None


@pytest.mark.asyncio
async def test_judge_returns_none_for_empty_output(monkeypatch) -> None:
    monkeypatch.setattr(settings, "use_llm_judge", True)
    result = await judge_trace(_fake_trace(output=""))
    assert result is None


@pytest.mark.asyncio
async def test_judge_parses_valid_json(monkeypatch) -> None:
    monkeypatch.setattr(settings, "use_llm_judge", True)
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_completion('{"score": 0.82, "reasoning": "clear and accurate"}')
    )
    with patch("app.judge.get_client", return_value=mock_client):
        result = await judge_trace(_fake_trace())
    assert result is not None
    assert result.dimension == "judgment"
    assert result.score == 0.82
    assert "clear" in result.reasoning


@pytest.mark.asyncio
async def test_judge_clamps_score_to_range(monkeypatch) -> None:
    monkeypatch.setattr(settings, "use_llm_judge", True)
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_completion('{"score": 1.7, "reasoning": "too high"}')
    )
    with patch("app.judge.get_client", return_value=mock_client):
        result = await judge_trace(_fake_trace())
    assert result is not None
    assert result.score == 1.0


@pytest.mark.asyncio
async def test_judge_returns_none_on_malformed_json(monkeypatch) -> None:
    monkeypatch.setattr(settings, "use_llm_judge", True)
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_completion("this is not JSON at all")
    )
    with patch("app.judge.get_client", return_value=mock_client):
        result = await judge_trace(_fake_trace())
    assert result is None


@pytest.mark.asyncio
async def test_judge_returns_none_on_llm_error(monkeypatch) -> None:
    monkeypatch.setattr(settings, "use_llm_judge", True)
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=RuntimeError("rate limit")
    )
    with patch("app.judge.get_client", return_value=mock_client):
        result = await judge_trace(_fake_trace())
    assert result is None


@pytest.mark.asyncio
async def test_judge_feature_flag_off_by_default() -> None:
    assert settings.use_llm_judge is False
