import logging
import os

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Arca, a reliable assistant.
Answer clearly and concisely. If you don't know something, say so."""

AGENT_ID = "agent-1"

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _client


async def run(message: str) -> tuple[str, str]:
    """Returns (response_text, prompt_used)"""
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": message},
    ]
    prompt_used = f"[system]: {SYSTEM_PROMPT}\n[user]: {message}"

    client = get_client()
    completion = await client.chat.completions.create(
        model=model,
        messages=messages,
    )
    response_text = completion.choices[0].message.content or ""
    logger.info("Agent %s responded to message (len=%d)", AGENT_ID, len(response_text))
    return response_text, prompt_used
