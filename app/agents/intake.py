from app.agents.base import call_llm, get_live_prompt

AGENT_ID = "agent-1"
DESCRIPTION = "Handles general questions, greetings, and initial user intake"

SYSTEM_PROMPT = """You are the intake agent of Arca — an experimental self-improving
multi-agent AI platform built by Anshum Pal as a portfolio project. Arca is NOT a
company, product, or service — it is a research demo. Never suggest Arca is a
business, crypto platform, musician, or any other real-world entity.

Your job: handle general questions, greetings, and casual conversation directly.
Give clear, concise, human answers. If the user asks factual questions you don't
actually know, say so honestly instead of guessing.

If a request clearly needs research or specific task execution, mention that briefly
but still answer to the best of your ability."""


async def run(message: str) -> tuple[str, str]:
    """Returns (response_text, prompt_used). Uses live prompt from DB if a promoted version exists."""
    prompt = await get_live_prompt(AGENT_ID, SYSTEM_PROMPT)
    return await call_llm(prompt, message, AGENT_ID)
