import logging
import time

from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None

# ─── In-memory prompt cache (Phase 6) ─────────────────────────────────────────
_prompt_cache: dict[str, tuple[str, float]] = {}
CACHE_TTL_SECONDS = 30

# ─── Deprecated-model auto-remap (hotfix) ─────────────────────────────────────
# Groq periodically deprecates model names. When a request fails with
# model_not_found, retry once using the healthy fallback below. This means
# production keeps working even if OPENAI_MODEL env var points at a dead name.
FALLBACK_MODEL = "llama-3.3-70b-versatile"

# Known-dead model names that should be immediately swapped before ever calling
# the API. Extend this list as providers deprecate more.
DEPRECATED_MODELS = {
    "llama-3.1-8b-instant",
    "llama-3.1-70b-versatile",
    "mixtral-8x7b-32768",
    "llama3-8b-8192",
    "llama3-70b-8192",
    "gemma-7b-it",
}


def _resolve_model() -> str:
    """Pick the model to use — auto-remap deprecated names to the fallback."""
    configured = settings.openai_model
    if configured in DEPRECATED_MODELS:
        logger.warning(
            "OPENAI_MODEL='%s' is deprecated — auto-remapping to '%s'",
            configured, FALLBACK_MODEL,
        )
        return FALLBACK_MODEL
    return configured


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

    Model resolution order:
      1. _resolve_model() — auto-remaps known-deprecated names before the call
      2. On any model_not_found runtime error, retry ONCE with FALLBACK_MODEL

    This makes production resilient to Groq deprecating models we haven't
    yet updated in the OPENAI_MODEL env var.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message},
    ]
    prompt_used = f"[system]: {system_prompt}\n[user]: {message}"
    client = get_client()
    model = _resolve_model()

    try:
        completion = await client.chat.completions.create(
            model=model,
            messages=messages,
        )
    except Exception as first_exc:
        # If the model is deprecated at runtime (not in our static list yet),
        # fall back to the known-healthy model and log loudly.
        msg_lower = str(first_exc).lower()
        is_model_error = "model_not_found" in msg_lower or "does not exist" in msg_lower
        if is_model_error and model != FALLBACK_MODEL:
            logger.warning(
                "Agent %s: model '%s' rejected at runtime — retrying with '%s'",
                agent_id, model, FALLBACK_MODEL,
            )
            completion = await client.chat.completions.create(
                model=FALLBACK_MODEL,
                messages=messages,
            )
        else:
            raise

    response_text = completion.choices[0].message.content or ""
    logger.info("Agent %s responded (len=%d chars)", agent_id, len(response_text))
    return response_text, prompt_used
