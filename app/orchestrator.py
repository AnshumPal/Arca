import logging

from app import agent

logger = logging.getLogger(__name__)


async def handle(message: str, session_id: str | None) -> tuple[str, str]:
    """Call the agent and return (response_text, prompt_used)."""
    logger.info("Orchestrator handling message for session=%s", session_id)
    response_text, prompt_used = await agent.run(message)
    return response_text, prompt_used
