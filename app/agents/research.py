from app.agents.base import call_llm

AGENT_ID = "agent-2"
DESCRIPTION = "Handles research, analysis, comparisons, and information synthesis"

SYSTEM_PROMPT = """You are Arca's research agent. You are given tasks that require
gathering, analysing, and synthesising information. Provide structured, accurate,
well-reasoned responses. Use bullet points or sections when the answer is complex."""


async def run(message: str) -> tuple[str, str]:
    """Returns (response_text, prompt_used)"""
    return await call_llm(SYSTEM_PROMPT, message, AGENT_ID)
