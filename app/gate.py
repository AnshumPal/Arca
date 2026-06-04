"""
gate.py
The promotion gate. Every sandbox runs through 4 checks before promotion.
Gate results are stored in the promotion record — the human sees exactly
why a promotion would pass or fail before deciding.

Pure check logic — no DB writes (only reads).
"""

import dataclasses
import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SandboxAgent

logger = logging.getLogger(__name__)

# Gate thresholds — every check must pass for gate_passed = True
GATE_THRESHOLDS = {
    "min_traces":              10,
    "min_overall_delta":       0.05,
    "min_error_score":         0.80,
    "max_latency_regression": -0.10,  # sandbox latency can drop at most 0.10 vs prod
}


@dataclass
class GateCheck:
    name:      str
    passed:    bool
    value:     float | int | str
    threshold: float | int | str
    message:   str


@dataclass
class GateResult:
    passed:  bool
    summary: str
    checks:  list[GateCheck] = dataclasses.field(default_factory=list)


def to_dict(result: GateResult) -> dict:
    """Serialize GateResult for JSONB storage."""
    return {
        "passed":  result.passed,
        "summary": result.summary,
        "checks":  [dataclasses.asdict(c) for c in result.checks],
    }


async def run_gate(sandbox_id: str, db: AsyncSession) -> GateResult:
    """
    Runs all 4 gate checks. Returns GateResult with passed=True only if every check passes.
    """
    sid = uuid.UUID(sandbox_id) if isinstance(sandbox_id, str) else sandbox_id

    # Fetch sandbox
    result = await db.execute(select(SandboxAgent).where(SandboxAgent.id == sid))
    sandbox = result.scalar_one_or_none()
    if sandbox is None:
        raise ValueError(f"Sandbox not found: {sandbox_id}")

    checks: list[GateCheck] = []

    # ─── Check 1: minimum shadow traces ───────────────────────────────────
    count_result = await db.execute(
        text("SELECT COUNT(*) FROM sandbox_traces WHERE sandbox_id = :sid"),
        {"sid": str(sid)},
    )
    trace_count = count_result.scalar() or 0
    min_traces = GATE_THRESHOLDS["min_traces"]
    c1_passed = trace_count >= min_traces
    checks.append(GateCheck(
        name="min_traces",
        passed=c1_passed,
        value=int(trace_count),
        threshold=int(min_traces),
        message=(
            f"{trace_count} shadow traces — sufficient data"
            if c1_passed
            else f"Insufficient data: only {trace_count} shadow traces. Need at least {min_traces}."
        ),
    ))

    # Fetch sandbox averages
    sb_stmt = text(
        """
        SELECT
            AVG(overall_score)                                     AS overall,
            AVG(CASE WHEN dimension = 'latency' THEN score END)   AS latency,
            AVG(CASE WHEN dimension = 'error'   THEN score END)   AS error
        FROM sandbox_eval_scores
        WHERE sandbox_id = :sid
        """
    )
    sb_result = await db.execute(sb_stmt, {"sid": str(sid)})
    sb_row = sb_result.fetchone()

    # Fetch production averages for the same agent
    prod_stmt = text(
        """
        SELECT
            AVG(er.overall_score)                                       AS overall,
            AVG(CASE WHEN es.dimension = 'latency' THEN es.score END)  AS latency,
            AVG(CASE WHEN es.dimension = 'error'   THEN es.score END)  AS error
        FROM eval_runs er
        JOIN eval_scores es ON es.eval_run_id = er.id
        WHERE er.agent_id = :agent_id
        """
    )
    prod_result = await db.execute(prod_stmt, {"agent_id": sandbox.production_agent_id})
    prod_row = prod_result.fetchone()

    def _val(row, col: str) -> float:
        v = getattr(row, col, None) if row else None
        return float(v) if v is not None else 0.0

    sb_overall = _val(sb_row, "overall")
    sb_latency = _val(sb_row, "latency")
    sb_error   = _val(sb_row, "error")
    pr_overall = _val(prod_row, "overall")
    pr_latency = _val(prod_row, "latency")

    # ─── Check 2: overall score improvement ───────────────────────────────
    delta_overall = round(sb_overall - pr_overall, 4)
    min_delta = GATE_THRESHOLDS["min_overall_delta"]
    c2_passed = delta_overall >= min_delta
    checks.append(GateCheck(
        name="min_overall_delta",
        passed=c2_passed,
        value=delta_overall,
        threshold=min_delta,
        message=(
            f"Sandbox outperforms production by {delta_overall:.3f}"
            if c2_passed
            else f"Sandbox not meaningfully better: delta {delta_overall:.3f}, need >= {min_delta}"
        ),
    ))

    # ─── Check 3: error score safety ──────────────────────────────────────
    min_err = GATE_THRESHOLDS["min_error_score"]
    c3_passed = sb_error >= min_err
    checks.append(GateCheck(
        name="min_error_score",
        passed=c3_passed,
        value=round(sb_error, 4),
        threshold=min_err,
        message=(
            f"Error score {sb_error:.2f} meets safety threshold {min_err}"
            if c3_passed
            else f"Error score {sb_error:.2f} below safety threshold {min_err}"
        ),
    ))

    # ─── Check 4: latency regression guard ────────────────────────────────
    delta_latency = round(sb_latency - pr_latency, 4)
    max_regression = GATE_THRESHOLDS["max_latency_regression"]
    c4_passed = delta_latency >= max_regression
    checks.append(GateCheck(
        name="max_latency_regression",
        passed=c4_passed,
        value=delta_latency,
        threshold=max_regression,
        message=(
            f"Latency delta {delta_latency:.2f} within acceptable range"
            if c4_passed
            else f"Latency regression: sandbox {sb_latency:.2f} vs production {pr_latency:.2f}, delta {delta_latency:.2f}"
        ),
    ))

    passed_count = sum(1 for c in checks if c.passed)
    all_passed = passed_count == len(checks)
    summary = (
        f"Gate passed: all {len(checks)} checks succeeded"
        if all_passed
        else f"Gate failed: {len(checks) - passed_count} of {len(checks)} checks failed"
    )

    return GateResult(passed=all_passed, summary=summary, checks=checks)
