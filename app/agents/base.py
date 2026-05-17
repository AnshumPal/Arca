import logging

from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    """Shared OpenAI/Groq client — created once and reused."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,  # None = default OpenAI
        )
    return _client


async def call_llm(system_prompt: str, message: str, agent_id: str) -> tuple[str, str]:
    """
    Shared LLM call used by all agents.
    Returns (response_text, prompt_used).
    prompt_used is the full prompt string stored in the trace.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message},
    ]
    prompt_used = f"[system]: {system_prompt}\n[user]: {message}"

    client = get_client()
    completion = await client.chat.completions.create(
        model=settings.openai_model,
        messages=messages,
    )
    response_text = completion.choices[0].message.content or ""
    logger.info("Agent %s responded (len=%d chars)", agent_id, len(response_text))
    return response_text, prompt_used
