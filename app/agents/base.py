import logging
import time

from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None

# ─── In-memory prompt cache (Phase 6) ─────────────────────────────────────────
# Each entry: agent_id → (resolved_prompt, cached_at_timestamp)
# Live within CACHE_TTL_SECONDS — invalidated explicitly on promotion / rollback.
_prompt_cache: dict[str, tuple[str, float]] = {}
CACHE_TTL_SECONDS = 30


def get_client() -> AsyncOpenAI:
    """Shared OpenAI/Groq client — created once and reused."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )
    return _client


def invalidate_prompt_cache(agent_id: str | None = None) -> None:
    """Drop a single agent (or all) from the cache. Called after promotion / rollback."""
    if agent_id is None:
        _prompt_cache.clear()
    else:
        _prompt_cache.pop(agent_id, None)


async def get_live_prompt(agent_id: str, hardcoded_prompt: str) -> str:
    """
    Resolve the live system prompt for an agent.
    Checks DB for current AgentVersion; falls back to hardcoded prompt if none.
    Uses a short TTL cache (30s) to keep chat latency unaffected.
    """
    now = time.time()
    if agent_id in _prompt_cache:
        cached, cached_at = _prompt_cache[agent_id]
        if now - cached_at < CACHE_TTL_SECONDS:
            return cached

    # Lazy imports to avoid circular dependency at module load
    from app import version_manager
    from app.database import AsyncSessionLocal

    live: str | None = None
    try:
        async with AsyncSessionLocal() as db:
            live = await version_manager.get_current_prompt(agent_id, db)
    except Exception as exc:
        logger.warning("Could not fetch live prompt for %s: %s — falling back", agent_id, exc)
        live = None

    result = live if live else hardcoded_prompt
    _prompt_cache[agent_id] = (result, now)
    return result


async def call_llm(system_prompt: str, message: str, agent_id: str) -> tuple[str, str]:
    """
    Shared LLM call used by all agents.
    Returns (response_text, prompt_used) — prompt_used is the live prompt.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message},
    ]
    prompt_used = f"[system]: {system_prompt}\n[user]: {message}"

    client = get_client()
    completion = await client.chat.completions.create(
        model=settings.openai_model,
        messages=messages,
    )
    response_text = completion.choices[0].message.content or ""
    logger.info("Agent %s responded (len=%d chars)", agent_id, len(response_text))
    return response_text, prompt_used
