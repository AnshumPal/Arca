from app.agents.base import call_llm, get_live_prompt

AGENT_ID = "agent-3"
DESCRIPTION = "Handles task execution, workflow steps, and structured output generation"

SYSTEM_PROMPT = """You are Arca's action agent. You execute specific tasks and
return structured, actionable output. Be precise. If a task is ambiguous,
ask one clarifying question before proceeding."""


async def run(message: str) -> tuple[str, str]:
    """Returns (response_text, prompt_used). Uses live prompt from DB if a promoted version exists."""
    prompt = await get_live_prompt(AGENT_ID, SYSTEM_PROMPT)
    return await call_llm(prompt, message, AGENT_ID)
