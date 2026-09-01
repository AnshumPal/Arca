"""
judge.py
Phase 9 — LLM-as-judge quality dimension.

The Phase 3 evaluator scores latency, length, feedback, and error — all pure,
deterministic, no LLM cost. What it CANNOT measure: whether the answer was
actually accurate, helpful, or on-topic. That's the semantic gap.

This module adds a fifth optional dimension called `judgment` that sends
(input, output) to an LLM and asks for a 0.0-1.0 rating with a short reason.
It runs AFTER the deterministic evaluator, is feature-flagged via
USE_LLM_JUDGE, and never blocks or crashes the main eval pipeline —
failures are logged and the trace keeps its 4-dimension score.

Design decisions:
- Separate file, not merged into evaluator.py, to preserve the "pure function"
  guarantee of that module
- One LLM call per evaluated trace when enabled
- Strict JSON response format for reliable parsing
- Wrapped in try/except everywhere — a broken judge never breaks eval
- The judgment dimension does NOT feed into the DIMENSION_WEIGHTS overall
  score by default (would double-count LLM opinion). It's reported separately
  and can be viewed via GET /eval/scores.
"""

import json
import logging
from dataclasses import dataclass
from typing import Optional

from app.agents.base import get_client
from app.config import settings
from app.models import Trace

logger = logging.getLogger(__name__)

JUDGE_SYSTEM_PROMPT = """You are a strict evaluator of AI assistant responses.

You will be given:
1. The user's input
2. The assistant's response

Rate the response on a single 0.0-1.0 scale considering:
- Accuracy (did it answer what was asked, without fabricating facts?)
- Helpfulness (did it actually help the user, not just deflect?)
- Relevance (did it stay on topic?)

Scale:
- 1.0 = excellent — accurate, helpful, on-topic
- 0.7 = good — mostly right, minor issues
- 0.5 = mediocre — partially helpful or vague
- 0.3 = weak — mostly unhelpful or off-topic
- 0.0 = harmful — wrong, hallucinated, or evasive

Respond in this EXACT JSON format, no other text:
{"score": 0.0, "reasoning": "one short sentence"}"""


@dataclass
class JudgmentResult:
    dimension: str = "judgment"
    score: float = 0.5
    reasoning: str = ""


async def judge_trace(trace: Trace) -> Optional[JudgmentResult]:
    """
    Send (trace.input, trace.output) to the LLM and return a JudgmentResult.
    Returns None if judgment is disabled, or if the trace has no output to score,
    or if the LLM call fails.
    """
    if not settings.use_llm_judge:
        return None

    if not trace.output or not trace.output.strip():
        # Nothing to judge — the error dimension already covers empty outputs
        return None

    # Truncate very long outputs to keep the judge call cheap
    output_snippet = trace.output[:2000]
    input_snippet = (trace.input or "")[:500]

    user_message = f"User input:\n{input_snippet}\n\nAssistant response:\n{output_snippet}"

    try:
        client = get_client()
        completion = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {"role": "user",   "content": user_message},
            ],
            max_tokens=120,
            temperature=0,
        )
        raw = (completion.choices[0].message.content or "").strip()
    except Exception as exc:
        logger.error("Judge LLM call failed for trace %s: %s", trace.id, exc)
        return None

    # Strip markdown fences if the model wrapped its JSON
    cleaned = raw
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    cleaned = cleaned.strip()

    try:
        parsed = json.loads(cleaned)
        score = float(parsed["score"])
        reasoning = str(parsed.get("reasoning", "")).strip()
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
        logger.warning(
            "Judge returned malformed output for trace %s: %s | raw=%s",
            trace.id, exc, raw[:200],
        )
        return None

    # Clamp defensively
    score = max(0.0, min(1.0, score))

    return JudgmentResult(score=round(score, 4), reasoning=reasoning[:500])
