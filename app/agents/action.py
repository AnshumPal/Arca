from app.agents.base import call_llm

AGENT_ID = "agent-3"
DESCRIPTION = "Handles task execution, workflow steps, and structured output generation"

SYSTEM_PROMPT = """You are Arca's action agent. You execute specific tasks and
return structured, actionable output. Be precise. If a task is ambiguous,
ask one clarifying question before proceeding."""


async def run(message: str) -> tuple[str, str]:
    """Returns (response_text, prompt_used)"""
    return await call_llm(SYSTEM_PROMPT, message, AGENT_ID)
