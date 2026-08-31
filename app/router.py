import logging

logger = logging.getLogger(__name__)

# ─── Phase 7 fix: intercept queries about Arca itself ────────────────────────
# Small LLMs confabulate about "Arca" because the name collides with a real
# musician and a crypto company. Short-circuit these questions before they hit
# any agent — return a canned truthful answer instead.
ARCA_SELF_KEYWORDS = [
    "what is arca", "what's arca", "whats arca",
    "who is arca", "who's arca", "whos arca",
    "about arca", "arca means", "define arca",
    "explain arca", "tell me about arca", "arca is what",
    "what does arca do", "how does arca work",
]

RESEARCH_KEYWORDS = [
    "research", "analyse", "analyze", "compare", "explain", "summarise",
    "summarize", "what is", "how does", "why does", "difference between",
    "pros and cons", "overview", "history of",
]

ACTION_KEYWORDS = [
    "create", "write", "generate", "build", "make", "draft",
    "list", "format", "convert", "extract", "produce", "output",
]


def classify(message: str) -> str:
    """
    Classifies a user message and returns the appropriate agent_id.
    Uses keyword heuristics — no extra LLM call needed.

    Returns:
        'arca-info' — canned truthful answer (bypasses LLM to avoid hallucination)
        'agent-3'   — action agent (task execution)
        'agent-2'   — research agent (analysis / synthesis)
        'agent-1'   — intake agent (default / general)
    """
    msg = message.lower().strip()

    # Highest priority: intercept meta-questions about Arca itself
    if any(k in msg for k in ARCA_SELF_KEYWORDS):
        logger.debug("Router → arca-info (self-query intercepted)")
        return "arca-info"

    if any(k in msg for k in ACTION_KEYWORDS):
        logger.debug("Router → agent-3 (action) for message: %s", message[:60])
        return "agent-3"

    if any(k in msg for k in RESEARCH_KEYWORDS):
        logger.debug("Router → agent-2 (research) for message: %s", message[:60])
        return "agent-2"

    logger.debug("Router → agent-1 (intake/default) for message: %s", message[:60])
    return "agent-1"
