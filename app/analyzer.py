"""
analyzer.py
Reads eval and trace data to find failure patterns per agent.
Pure analysis — no LLM calls, no DB writes.
Returns structured FailurePattern objects.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import REGISTRY

logger = logging.getLogger(__name__)

# If a dimension avg falls below these thresholds, it is a failure pattern
FAILURE_THRESHOLDS: dict[str, float] = {
    "latency":  0.60,
    "length":   0.65,
    "feedback": 0.55,
    "error":    0.85,   # higher bar — errors are serious
}


@dataclass
class FailurePattern:
    agent_id:      str
    dimension:     str
    avg_score:     float
    threshold:     float
    sample_count:  int
    sample_inputs: list[str] = field(default_factory=list)
    diagnosis:     str = ""


async def analyze_agent(
    agent_id: str,
    db: AsyncSession,
    lookback_days: int = 7,
) -> list[FailurePattern]:
    """
    Analyzes eval scores for one agent over the last `lookback_days` days.
    For each dimension below threshold:
      1. Calculate avg score for that dimension
      2. Find the 5 traces with the lowest scores on that dimension
      3. Extract the input text from those traces
      4. Build a FailurePattern
    Returns list of FailurePattern — empty list if agent is healthy.
    """
    since = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    # Get per-dimension averages for this agent in the lookback window
    avg_stmt = text(
        """
        SELECT
            es.dimension,
            AVG(es.score)  AS avg_score,
            COUNT(*)       AS sample_count
        FROM eval_scores es
        JOIN eval_runs er ON er.id = es.eval_run_id
        WHERE er.agent_id   = :agent_id
          AND er.evaluated_at >= :since
        GROUP BY es.dimension
        """
    )
    avg_result = await db.execute(avg_stmt, {"agent_id": agent_id, "since": since})
    rows = avg_result.fetchall()

    patterns: list[FailurePattern] = []

    for row in rows:
        dimension   = row.dimension
        avg_score   = float(row.avg_score)
        sample_count = int(row.sample_count)
        threshold   = FAILURE_THRESHOLDS.get(dimension, 0.60)

        if avg_score >= threshold:
            continue  # healthy — skip

        # Find 5 worst-performing inputs for this dimension
        worst_stmt = text(
            """
            SELECT t.input, es.score
            FROM eval_scores es
            JOIN eval_runs er ON er.id = es.eval_run_id
            JOIN traces t     ON t.id  = er.trace_id
            WHERE er.agent_id    = :agent_id
              AND es.dimension   = :dimension
              AND er.evaluated_at >= :since
            ORDER BY es.score ASC
            LIMIT 5
            """
        )
        worst_result = await db.execute(
            worst_stmt,
            {"agent_id": agent_id, "dimension": dimension, "since": since},
        )
        worst_rows = worst_result.fetchall()
        sample_inputs = [r.input[:200] for r in worst_rows]  # trim long inputs

        diagnosis = (
            f"{agent_id} {dimension} avg {avg_score:.2f} — "
            f"below threshold {threshold:.2f} across {sample_count} traces"
        )

        patterns.append(
            FailurePattern(
                agent_id=agent_id,
                dimension=dimension,
                avg_score=round(avg_score, 4),
                threshold=threshold,
                sample_count=sample_count,
                sample_inputs=sample_inputs,
                diagnosis=diagnosis,
            )
        )

    if patterns:
        logger.info(
            "Analyzer found %d failure pattern(s) for %s", len(patterns), agent_id
        )

    return patterns


async def analyze_all_agents(
    db: AsyncSession,
    lookback_days: int = 7,
) -> list[FailurePattern]:
    """Runs analyze_agent() for all production agents. Returns combined failure patterns."""
    all_patterns: list[FailurePattern] = []
    for agent_id in REGISTRY:
        patterns = await analyze_agent(agent_id, db, lookback_days=lookback_days)
        all_patterns.extend(patterns)
    logger.info(
        "Analyzer complete — %d total failure pattern(s) across %d agents",
        len(all_patterns),
        len(REGISTRY),
    )
    return all_patterns
