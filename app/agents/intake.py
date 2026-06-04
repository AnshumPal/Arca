from app.agents.base import call_llm, get_live_prompt

AGENT_ID = "agent-1"
DESCRIPTION = "Handles general questions, greetings, and initial user intake"

SYSTEM_PROMPT = """You are Arca's intake agent. You handle general questions,
clarify user intent, and provide clear, concise answers.
If a request requires research or a specific action, say so clearly."""


async def run(message: str) -> tuple[str, str]:
    """Returns (response_text, prompt_used). Uses live prompt from DB if a promoted version exists."""
    prompt = await get_live_prompt(AGENT_ID, SYSTEM_PROMPT)
    return await call_llm(prompt, message, AGENT_ID)
