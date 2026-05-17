from app.agents.base import call_llm

AGENT_ID = "agent-1"
DESCRIPTION = "Handles general questions, greetings, and initial user intake"

SYSTEM_PROMPT = """You are Arca's intake agent. You handle general questions,
clarify user intent, and provide clear, concise answers.
If a request requires research or a specific action, say so clearly."""


async def run(message: str) -> tuple[str, str]:
    """Returns (response_text, prompt_used)"""
    return await call_llm(SYSTEM_PROMPT, message, AGENT_ID)
