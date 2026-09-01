"""
proposer.py
Uses the OpenAI API to generate improved system prompt variants
based on identified failure patterns.

This is the ONE place in Phase 5 where an LLM call is made.
Exactly one call per failure pattern per optimizer run.
"""

import json
import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import _resolve_model, get_client
from app.analyzer import FailurePattern
from app.config import settings

logger = logging.getLogger(__name__)

PROPOSER_SYSTEM_PROMPT = """You are an AI agent optimizer.

You will be given:
1. An agent's current system prompt
2. A failure pattern — a dimension where the agent is underperforming
3. Sample inputs where the agent scored lowest on that dimension

Your job: propose ONE improved system prompt that directly addresses the failure.

Rules:
- Keep the agent's core identity and purpose unchanged
- Only change what is necessary to fix the specific failure pattern
- Be specific — vague changes don't help
- The new prompt must be self-contained (don't reference "the previous prompt")

Respond in this exact JSON format:
{
  "proposed_prompt": "the full new system prompt text",
  "reasoning": "one paragraph explaining what you changed and why it should improve the score"
}"""

# Maps dimension → coaching hint sent to the proposer
_DIMENSION_HINTS: dict[str, str] = {
    "latency":  "The agent is responding too slowly. Focus on brevity — shorter, more direct responses.",
    "length":   "The response length is outside the ideal range. Calibrate output length to match the query complexity.",
    "feedback": "Users are rating responses negatively. Focus on being more helpful, accurate, and user-friendly.",
    "error":    "The agent is producing errors or empty responses. Add robustness — always produce output, handle ambiguous inputs gracefully.",
}


@dataclass
class OptimizationProposal:
    agent_id:        str
    dimension:       str
    original_prompt: str
    proposed_prompt: str
    reasoning:       str
    sandbox_config:  dict


async def propose_improvement(
    pattern: FailurePattern,
    current_prompt: str,
    db: AsyncSession,
) -> OptimizationProposal:
    """
    Builds a user message describing the failure pattern + sample inputs,
    calls OpenAI once, parses JSON response.
    Raises ValueError if OpenAI call fails or JSON is malformed.
    """
    hint = _DIMENSION_HINTS.get(pattern.dimension, "Improve overall quality.")

    sample_block = "\n".join(
        f"{i + 1}. {inp}" for i, inp in enumerate(pattern.sample_inputs)
    ) or "No sample inputs available."

    user_message = (
        f"Agent: {pattern.agent_id}\n"
        f"Underperforming dimension: {pattern.dimension}\n"
        f"Current average score: {pattern.avg_score:.2f} (threshold: {pattern.threshold:.2f})\n"
        f"Improvement hint: {hint}\n"
        f"Number of traces analyzed: {pattern.sample_count}\n\n"
        f"Sample inputs where this agent scored lowest on {pattern.dimension}:\n"
        f"{sample_block}\n\n"
        f"Current system prompt:\n{current_prompt}\n\n"
        f"Propose an improved system prompt that addresses the {pattern.dimension} failure."
    )

    client = get_client()
    try:
        completion = await client.chat.completions.create(
            model=_resolve_model(),
            messages=[
                {"role": "system", "content": PROPOSER_SYSTEM_PROMPT},
                {"role": "user",   "content": user_message},
            ],
        )
        raw = completion.choices[0].message.content or ""
    except Exception as exc:
        raise ValueError(f"OpenAI call failed in proposer: {exc}") from exc

    # Parse JSON — strip markdown code fences if present
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    cleaned = cleaned.strip()

    try:
        parsed = json.loads(cleaned)
        proposed_prompt = parsed["proposed_prompt"]
        reasoning       = parsed["reasoning"]
    except (json.JSONDecodeError, KeyError) as exc:
        raise ValueError(
            f"Proposer returned invalid JSON for {pattern.agent_id}/{pattern.dimension}: {exc}\nRaw: {raw[:300]}"
        ) from exc

    logger.info(
        "Proposer generated improvement for %s/%s", pattern.agent_id, pattern.dimension
    )

    return OptimizationProposal(
        agent_id=pattern.agent_id,
        dimension=pattern.dimension,
        original_prompt=current_prompt,
        proposed_prompt=proposed_prompt,
        reasoning=reasoning,
        sandbox_config={
            "system_prompt": proposed_prompt,
            "model": _resolve_model(),   # never bake in a deprecated name
        },
    )
