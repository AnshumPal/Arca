"""
evaluator.py
Core evaluation logic for Arca Phase 3.
Scores a single trace across 4 dimensions and returns an EvalResult.
No external API calls — all scoring is deterministic from trace data.
"""

from dataclasses import dataclass, field

from app.models import Trace

# ─── Dimension weights ─────────────────────────────────────────────────────────

DIMENSION_WEIGHTS: dict[str, float] = {
    "latency":  0.20,
    "length":   0.25,
    "feedback": 0.35,   # highest weight — direct human signal
    "error":    0.20,
}

# Ideal word-count ranges per agent type
_IDEAL_RANGES: dict[str, tuple[int, int]] = {
    "agent-1": (50, 300),    # intake — conversational, concise
    "agent-2": (100, 600),   # research — detailed analysis
    "agent-3": (30, 400),    # action — task-focused output
}


# ─── Result dataclasses ────────────────────────────────────────────────────────

@dataclass
class DimensionResult:
    dimension: str
    score: float          # 0.0 to 1.0
    reasoning: str


@dataclass
class EvalResult:
    trace_id: str
    agent_id: str
    overall_score: float
    dimensions: list[DimensionResult] = field(default_factory=list)
    eval_version: str = "v1"


# ─── Dimension scorers ─────────────────────────────────────────────────────────

def score_latency(latency_ms: int | None) -> tuple[float, str]:
    """
    1.0  = under 800ms   (excellent)
    0.75 = 800–1500ms    (good)
    0.5  = 1500–3000ms   (acceptable)
    0.25 = 3000–5000ms   (slow)
    0.0  = over 5000ms   (unacceptable)
    """
    if latency_ms is None:
        return 0.5, "No latency recorded"
    if latency_ms < 800:
        return 1.0, f"Excellent latency: {latency_ms}ms"
    if latency_ms < 1500:
        return 0.75, f"Good latency: {latency_ms}ms"
    if latency_ms < 3000:
        return 0.5, f"Acceptable latency: {latency_ms}ms"
    if latency_ms < 5000:
        return 0.25, f"Slow response: {latency_ms}ms"
    return 0.0, f"Unacceptable latency: {latency_ms}ms"


def score_length(input_text: str, output_text: str | None, agent_id: str) -> tuple[float, str]:
    """
    Checks output is neither too short (unhelpful) nor too long (rambling).
    Thresholds differ by agent type.

    Score 1.0 = within ideal range
    Score 0.5 = outside ideal but not extreme (within 2x upper bound)
    Score 0.0 = empty output or extreme length (over 5x upper bound)
    """
    if not output_text or output_text.strip() == "":
        return 0.0, "Empty output — no length to score"

    low, high = _IDEAL_RANGES.get(agent_id, (50, 400))
    word_count = len(output_text.split())

    if low <= word_count <= high:
        return 1.0, f"Within ideal range: {word_count} words (ideal: {low}–{high})"

    if word_count > high * 5:
        return 0.0, f"Extreme length: {word_count} words (ideal: {low}–{high})"

    # Outside ideal but not extreme
    direction = "short" if word_count < low else "long"
    return 0.5, f"Slightly {direction}: {word_count} words (ideal: {low}–{high})"


def score_feedback(feedback: int | None) -> tuple[float, str]:
    """
    1.0  = feedback == 1   (explicit positive)
    0.5  = feedback is None (no signal — neutral)
    0.0  = feedback == -1  (explicit negative)
    """
    if feedback == 1:
        return 1.0, "User gave positive feedback"
    if feedback == -1:
        return 0.0, "User gave negative feedback"
    return 0.5, "No user feedback recorded"


def score_error(error: str | None, output: str | None) -> tuple[float, str]:
    """
    1.0 = no error, output exists
    0.5 = no error but output is empty/None (suspicious)
    0.0 = error field is populated (agent failed)
    """
    if error:
        return 0.0, f"Agent error: {error[:100]}"
    if not output or output.strip() == "":
        return 0.5, "No error but output is empty"
    return 1.0, "Clean completion"


def calculate_overall(scores: dict[str, float]) -> float:
    """Weighted average of all dimension scores. Returns 0.0–1.0."""
    return sum(scores[dim] * weight for dim, weight in DIMENSION_WEIGHTS.items())


# ─── Main entry point ──────────────────────────────────────────────────────────

def evaluate_trace(trace: Trace) -> EvalResult:
    """
    Pure function — no DB calls, no side effects.
    Takes a Trace ORM object, returns an EvalResult with all dimension scores.
    DB writes happen in eval_runner only.
    """
    latency_score,  latency_reason  = score_latency(trace.latency_ms)
    length_score,   length_reason   = score_length(trace.input, trace.output, trace.agent_id)
    feedback_score, feedback_reason = score_feedback(trace.feedback)
    error_score,    error_reason    = score_error(trace.error, trace.output)

    scores = {
        "latency":  latency_score,
        "length":   length_score,
        "feedback": feedback_score,
        "error":    error_score,
    }
    overall = calculate_overall(scores)

    dimensions = [
        DimensionResult("latency",  latency_score,  latency_reason),
        DimensionResult("length",   length_score,   length_reason),
        DimensionResult("feedback", feedback_score, feedback_reason),
        DimensionResult("error",    error_score,    error_reason),
    ]

    return EvalResult(
        trace_id=str(trace.id),
        agent_id=trace.agent_id,
        overall_score=round(overall, 4),
        dimensions=dimensions,
    )
