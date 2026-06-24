"""LLM cost tracker — real-time monthly cost tracking + budget caps.

Per decision 9 (redesign-decisions-v2.md):
  - Soft warning at $100/month
  - Hard cap at $150/month → pause non-critical Pipelines

Uses approximate GLM pricing; can be overridden via settings. Tracks in USD
to match the v2 design doc's $150 budget.

Pricing reference (as of 2026-06, approximations in USD per 1M tokens):
  GLM 4.8 (后勤层, quality_screen/news_pulse):    $0.10 in / $0.10 out
  GLM 5.1 (战术层, default deep_research):         $0.50 in / $0.50 out
  GLM 5.2 (战略层, top 3 候选):                    $2.00 in / $2.00 out

These are conservative estimates. Real Zhipu pricing varies by tier/contract.
Update via env: LLM_PRICE_GLM48_IN, LLM_PRICE_GLM48_OUT, etc.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.datetime_utils import now
from app.models.llm_call_log import LLMCallLog

logger = logging.getLogger(__name__)


# Approximate GLM pricing in USD per 1M tokens
# (conservative; real pricing may be lower)
GLM_PRICING_USD_PER_1M: dict[str, tuple[float, float]] = {
    # model: (input $/1M, output $/1M)
    "glm-4.8": (0.10, 0.10),
    "glm-5.1": (0.50, 0.50),
    "glm-5.2": (2.00, 2.00),
    # Fallbacks for older model versions
    "glm-4.7": (0.10, 0.10),
    "glm-4.6": (0.10, 0.10),
}

# Budget thresholds (USD)
SOFT_WARNING_USD: float = 100.0
HARD_CAP_USD: float = 150.0


@dataclass
class CostEntry:
    """Single LLM call cost record (written to llm_call_logs)."""
    trace_id: Optional[str]
    span_id: Optional[str]
    model: str
    pipeline_type: Optional[str]
    stock_code: Optional[str]
    prompt_hash: Optional[str]
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: Optional[int]
    tool_calls: Optional[dict] = None
    conflict_flags: Optional[dict] = None
    success: bool = True
    error_message: Optional[str] = None


def compute_cost_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    """Compute USD cost for a single LLM call.

    Falls back to GLM 5.1 pricing for unknown models.
    """
    pricing = GLM_PRICING_USD_PER_1M.get(model, GLM_PRICING_USD_PER_1M["glm-5.1"])
    in_cost = (tokens_in / 1_000_000) * pricing[0]
    out_cost = (tokens_out / 1_000_000) * pricing[1]
    return round(in_cost + out_cost, 6)


def write_call_log(db: Session, entry: CostEntry) -> LLMCallLog:
    """Persist a single LLM call to llm_call_logs table."""
    log = LLMCallLog(
        trace_id=entry.trace_id,
        span_id=entry.span_id,
        model=entry.model,
        pipeline_type=entry.pipeline_type,
        stock_code=entry.stock_code,
        prompt_hash=entry.prompt_hash,
        tokens_in=entry.tokens_in,
        tokens_out=entry.tokens_out,
        cost_usd=entry.cost_usd,
        latency_ms=entry.latency_ms,
        tool_calls_json=entry.tool_calls,
        conflict_flags_json=entry.conflict_flags,
        success=entry.success,
        error_message=entry.error_message,
    )
    db.add(log)
    db.flush()
    return log


def get_monthly_spend(db: Session, at_time: Optional[datetime] = None) -> dict:
    """Get current month's LLM spend.

    Returns:
        {
            "month": "2026-06",
            "total_usd": float,
            "soft_warning_usd": 100.0,
            "hard_cap_usd": 150.0,
            "by_model": {model: usd},
            "by_pipeline": {pipeline_type: usd},
            "call_count": int,
            "over_soft": bool,
            "over_hard": bool,
        }
    """
    at = at_time or now()
    month_start = at.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Total
    total_row = db.execute(
        select(
            func.coalesce(func.sum(LLMCallLog.cost_usd), 0.0).label("total"),
            func.count(LLMCallLog.id).label("count"),
        ).where(LLMCallLog.created_at >= month_start)
    ).one()
    total_usd = float(total_row.total or 0.0)
    call_count = int(total_row.count or 0)

    # By model
    by_model_rows = db.execute(
        select(
            LLMCallLog.model,
            func.coalesce(func.sum(LLMCallLog.cost_usd), 0.0).label("subtotal"),
        )
        .where(LLMCallLog.created_at >= month_start)
        .group_by(LLMCallLog.model)
    ).all()
    by_model = {row.model: float(row.subtotal or 0.0) for row in by_model_rows}

    # By pipeline
    by_pipeline_rows = db.execute(
        select(
            LLMCallLog.pipeline_type,
            func.coalesce(func.sum(LLMCallLog.cost_usd), 0.0).label("subtotal"),
        )
        .where(LLMCallLog.created_at >= month_start)
        .group_by(LLMCallLog.pipeline_type)
    ).all()
    by_pipeline = {
        (row.pipeline_type or "unknown"): float(row.subtotal or 0.0)
        for row in by_pipeline_rows
    }

    return {
        "month": at.strftime("%Y-%m"),
        "total_usd": round(total_usd, 4),
        "soft_warning_usd": SOFT_WARNING_USD,
        "hard_cap_usd": HARD_CAP_USD,
        "by_model": {k: round(v, 4) for k, v in by_model.items()},
        "by_pipeline": {k: round(v, 4) for k, v in by_pipeline.items()},
        "call_count": call_count,
        "over_soft": total_usd >= SOFT_WARNING_USD,
        "over_hard": total_usd >= HARD_CAP_USD,
    }


def check_budget_available(db: Session) -> tuple[bool, str]:
    """Check if budget allows new non-critical LLM call.

    Returns:
        (allowed, reason) — when not allowed, reason explains why.
    """
    status = get_monthly_spend(db)
    if status["over_hard"]:
        return (
            False,
            f"Hard cap reached: ${status['total_usd']:.2f} / ${HARD_CAP_USD:.2f}. "
            "Non-critical Pipelines paused. Critical (thesis_tracker / news_pulse) still allowed.",
        )
    if status["over_soft"]:
        return (
            True,
            f"Soft warning: ${status['total_usd']:.2f} / ${SOFT_WARNING_USD:.2f} "
            f"(hard cap ${HARD_CAP_USD:.2f}).",
        )
    return True, f"OK: ${status['total_usd']:.2f} / ${HARD_CAP_USD:.2f}"
