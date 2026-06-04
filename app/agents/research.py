from app.agents.base import call_llm, get_live_prompt

AGENT_ID = "agent-2"
DESCRIPTION = "Handles research, analysis, comparisons, and information synthesis"

SYSTEM_PROMPT = """You are Arca's research agent. You are given tasks that require
gathering, analysing, and synthesising information. Provide structured, accurate,
well-reasoned responses. Use bullet points or sections when the answer is complex."""


async def run(message: str) -> tuple[str, str]:
    """Returns (response_text, prompt_used). Uses live prompt from DB if a promoted version exists."""
    prompt = await get_live_prompt(AGENT_ID, SYSTEM_PROMPT)
    return await call_llm(prompt, message, AGENT_ID)
