import logging

logger = logging.getLogger(__name__)

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
        'agent-3' — action agent (task execution)
        'agent-2' — research agent (analysis / synthesis)
        'agent-1' — intake agent (default / general)
    """
    msg = message.lower()

    if any(k in msg for k in ACTION_KEYWORDS):
        logger.debug("Router → agent-3 (action) for message: %s", message[:60])
        return "agent-3"

    if any(k in msg for k in RESEARCH_KEYWORDS):
        logger.debug("Router → agent-2 (research) for message: %s", message[:60])
        return "agent-2"

    logger.debug("Router → agent-1 (intake/default) for message: %s", message[:60])
    return "agent-1"
