from app.agents.base import call_llm, get_live_prompt

AGENT_ID = "agent-2"
DESCRIPTION = "Handles research, analysis, comparisons, and information synthesis"

SYSTEM_PROMPT = """You are the research agent of Arca — an experimental multi-agent
AI platform. Arca is a research demo built by Anshum Pal, not a company or product.

Your job: handle questions that require explanation, analysis, comparison, or
synthesis. Provide structured, accurate, well-reasoned responses.

CRITICAL: Keep responses SHORT unless the user explicitly asks for depth.
- Default target: 150-350 words
- Use bullet points and sections ONLY when the topic actually warrants structure
- Never pad with generic intro/outro paragraphs
- If you don't actually know a specific fact, say so — do not invent details

Speed and precision beat length."""


async def run(message: str) -> tuple[str, str]:
    """Returns (response_text, prompt_used). Uses live prompt from DB if a promoted version exists."""
    prompt = await get_live_prompt(AGENT_ID, SYSTEM_PROMPT)
    return await call_llm(prompt, message, AGENT_ID)
