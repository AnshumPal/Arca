import logging

from app.agents import get_agent
from app.router import classify

logger = logging.getLogger(__name__)


async def handle(message: str, session_id: str | None) -> dict:
    """
    Classify the message, pick the right agent, run it.
    Returns a dict with agent_id, response, and prompt_used.
    """
    agent_id = classify(message)
    agent = get_agent(agent_id)
    logger.info("Orchestrator routing session=%s to %s", session_id, agent_id)
    response, prompt_used = await agent["run"](message)
    return {
        "agent_id": agent_id,
        "response": response,
        "prompt_used": prompt_used,
    }
