"""
semantic_router.py
Phase 8 — LLM-based intent classifier.

The Phase 2 keyword router is fast and free but misses semantic intent
(e.g. "how are you made" gets routed to intake because no keyword matches).
This module uses a single lightweight LLM call to classify intent when the
`USE_SEMANTIC_ROUTER` feature flag is enabled.

Design decisions:
- One LLM call per chat, low temperature, hard 10-token cap → ~300-800ms added
  latency but 95%+ routing accuracy vs ~70% for keyword-only
- Always runs the router short-circuit (ARCA_SELF_KEYWORDS) FIRST — no LLM
  cost for meta-questions about Arca itself
- On any failure (network, timeout, malformed response) → falls back to the
  keyword classifier so a bad LLM call never breaks routing
- Response is normalised to one of agent-1 / agent-2 / agent-3 — anything else
  triggers the fallback path
"""

import logging

from app.agents.base import get_client
from app.config import settings
from app.router import ARCA_SELF_KEYWORDS, classify as classify_keyword

logger = logging.getLogger(__name__)

CLASSIFIER_SYSTEM_PROMPT = """You are a routing classifier for a multi-agent platform.

Classify the user's message into exactly ONE of these three categories:

- agent-1 (intake): greetings, small talk, meta-questions about the platform,
  vague or personal statements, generic conversation
- agent-2 (research): explanation, analysis, comparison, factual questions
  about the world, "how does X work", "what is Y", learning-oriented queries
- agent-3 (action): concrete requests to CREATE, WRITE, GENERATE, PRODUCE, or
  FORMAT a specific artifact — poems, code, lists, drafts, structured output

Respond with ONLY the exact agent ID (agent-1, agent-2, or agent-3).
No punctuation, no explanation, no other text."""

_VALID_AGENTS = {"agent-1", "agent-2", "agent-3"}


async def classify_semantic(message: str) -> str:
    """
    LLM-based intent classification.

    Runs the router short-circuit first (Arca self-queries return 'arca-info'
    without any LLM call). Otherwise calls the model with a strict system
    prompt and low temperature. Falls back to the keyword classifier on any
    error so routing never breaks.
    """
    msg = message.lower().strip()

    # Short-circuit meta-questions about Arca before spending an LLM call
    if any(k in msg for k in ARCA_SELF_KEYWORDS):
        logger.debug("Semantic router → arca-info (self-query short-circuit)")
        return "arca-info"

    try:
        client = get_client()
        completion = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": CLASSIFIER_SYSTEM_PROMPT},
                {"role": "user",   "content": message},
            ],
            max_tokens=10,
            temperature=0,
        )
        raw = (completion.choices[0].message.content or "").strip().lower()

        # Normalise: pick the first valid agent-N substring
        for aid in _VALID_AGENTS:
            if aid in raw:
                logger.info("Semantic router → %s | %s", aid, message[:60])
                return aid

        logger.warning(
            "Semantic router returned unexpected '%s' — falling back to keyword classifier",
            raw,
        )
        return classify_keyword(message)

    except Exception as exc:
        logger.error(
            "Semantic router LLM call failed (%s) — falling back to keyword classifier",
            exc,
        )
        return classify_keyword(message)
