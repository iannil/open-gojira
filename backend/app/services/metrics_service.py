"""Phase 6 Tier 1 — Metrics aggregation service.

Aggregates raw observability data (PipelineRun, LLMCallLog) into
dashbordable metrics for the frontend MonitoringPage.

Tier 1 covers:
  - Pipeline success / failure rates per pipeline type
  - Full LLM call costs + token consumption
  - Conflict rate per pipeline (data_conflict_json)
  - Monthly cost vs budget (delegates to cost_tracker.get_monthly_spend)
"""

from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.datetime_utils import now
from app.models.llm_call_log import LLMCallLog
from app.models.pipeline import PipelineRun
from app.services.llm.cost_tracker import get_monthly_spend


# ── Pipeline metrics ─────────────────────────────────────────────────────────


def get_pipeline_summary(
    db: Session,
    days: int = 30,
) -> dict:
    """Aggregate pipeline run stats per pipeline type for the last N days.

    Returns:
        {
            "period_days": 30,
            "pipelines": {
                "valuations": {
                    "total": 10, "success": 8, "failed": 1, "running": 1,
                    "success_rate_pct": 80.0,
                    "avg_duration_ms": 12345,
                },
                ...
            },
            "overall": {"total": 20, "success_rate_pct": 75.0},
        }
    """
    cutoff = now() - timedelta(days=days)

    rows = db.execute(
        select(
            PipelineRun.pipeline_type,
            PipelineRun.status,
            func.count(PipelineRun.id).label("count"),
        )
        .where(PipelineRun.started_at >= cutoff)
        .group_by(PipelineRun.pipeline_type, PipelineRun.status)
    ).all()

    # Aggregate per pipeline
    pipelines: dict[str, dict] = {}
    overall_total = 0
    overall_success = 0

    for row in rows:
        ptype = row.pipeline_type or "unknown"
        if ptype not in pipelines:
            pipelines[ptype] = {"total": 0, "success": 0, "failed": 0, "running": 0, "other": 0}
        pipelines[ptype]["total"] += row.count
        overall_total += row.count

        if row.status == "success":
            pipelines[ptype]["success"] += row.count
            overall_success += row.count
        elif row.status == "failed":
            pipelines[ptype]["failed"] += row.count
        elif row.status in ("running", "pending"):
            pipelines[ptype]["running"] += row.count
        else:
            pipelines[ptype]["other"] += row.count

    # Compute rates + avg duration
    duration_rows = db.execute(
        select(
            PipelineRun.pipeline_type,
            func.avg(
                (func.unixepoch(PipelineRun.finished_at) - func.unixepoch(PipelineRun.started_at)) * 1000
            ).label("avg_ms"),
        )
        .where(
            PipelineRun.started_at >= cutoff,
            PipelineRun.status == "success",
            PipelineRun.finished_at.isnot(None),
        )
        .group_by(PipelineRun.pipeline_type)
    ).all()

    avg_durations = {r.pipeline_type: round(float(r.avg_ms or 0)) for r in duration_rows}

    result = {}
    for ptype, stats in pipelines.items():
        success_rate = round(stats["success"] / stats["total"] * 100, 1) if stats["total"] > 0 else 0.0
        result[ptype] = {
            **stats,
            "success_rate_pct": success_rate,
            "avg_duration_ms": avg_durations.get(ptype, 0),
        }

    return {
        "period_days": days,
        "pipelines": result,
        "overall": {
            "total": overall_total,
            "success_rate_pct": round(overall_success / overall_total * 100, 1) if overall_total > 0 else 0.0,
        },
    }


# ── LLM metrics ──────────────────────────────────────────────────────────────


def get_llm_summary(
    db: Session,
    days: int = 30,
) -> dict:
    """Aggregate LLM call stats for the last N days.

    Returns:
        {
            "period_days": 30,
            "total_calls": 150,
            "total_cost_usd": 12.34,
            "total_tokens_in": 500000,
            "total_tokens_out": 80000,
            "avg_latency_ms": 3200,
            "success_rate_pct": 98.5,
            "conflict_rate_pct": 3.2,
            "by_pipeline": {
                "deep_research": {"calls": 40, "cost_usd": 5.0, "conflict_rate_pct": 2.1},
                ...
            },
        }
    """
    cutoff = now() - timedelta(days=days)

    # Overall — use two queries for cross-dialect compatibility
    total_row = db.execute(
        select(func.count(LLMCallLog.id).label("total_calls"))
        .where(LLMCallLog.created_at >= cutoff)
    ).one()
    total_calls = int(total_row.total_calls or 0)

    cost_row = db.execute(
        select(
            func.coalesce(func.sum(LLMCallLog.cost_usd), 0.0).label("total_cost"),
            func.coalesce(func.sum(LLMCallLog.tokens_in), 0).label("total_tokens_in"),
            func.coalesce(func.sum(LLMCallLog.tokens_out), 0).label("total_tokens_out"),
            func.coalesce(func.avg(LLMCallLog.latency_ms), 0).label("avg_latency"),
        )
        .where(LLMCallLog.created_at >= cutoff)
    ).one()
    total_cost = float(cost_row.total_cost or 0.0)
    total_tokens_in = int(cost_row.total_tokens_in or 0)
    total_tokens_out = int(cost_row.total_tokens_out or 0)
    avg_latency = float(cost_row.avg_latency or 0.0)

    # Success count
    success_row = db.execute(
        select(func.count(LLMCallLog.id).label("success_count"))
        .where(LLMCallLog.created_at >= cutoff, LLMCallLog.success == True)
    ).one()
    success_count = int(success_row.success_count or 0)
    success_rate = round(success_count / total_calls * 100, 1) if total_calls > 0 else 0.0

    # Conflict rate — LLMCallLogs with non-empty conflict_flags_json
    conflict_row = db.execute(
        select(
            func.count(LLMCallLog.id).label("conflict_count"),
        )
        .where(
            LLMCallLog.created_at >= cutoff,
            LLMCallLog.conflict_flags_json.isnot(None),
            func.json_type(LLMCallLog.conflict_flags_json).isnot(None),
        )
    ).one()
    conflict_count = int(conflict_row.conflict_count or 0)
    conflict_rate = round(conflict_count / total_calls * 100, 1) if total_calls > 0 else 0.0

    # By pipeline
    by_pipeline_rows = db.execute(
        select(
            LLMCallLog.pipeline_type,
            func.count(LLMCallLog.id).label("calls"),
            func.coalesce(func.sum(LLMCallLog.cost_usd), 0.0).label("cost"),
            func.coalesce(func.sum(LLMCallLog.tokens_in), 0).label("tokens_in"),
            func.coalesce(func.sum(LLMCallLog.tokens_out), 0).label("tokens_out"),
        )
        .where(LLMCallLog.created_at >= cutoff)
        .group_by(LLMCallLog.pipeline_type)
    ).all()

    # Conflict rate by pipeline
    conflict_by_pipeline = {}
    conflict_by_pipeline_rows = db.execute(
        select(
            LLMCallLog.pipeline_type,
            func.count(LLMCallLog.id).label("conflict_count"),
        )
        .where(
            LLMCallLog.created_at >= cutoff,
            LLMCallLog.conflict_flags_json.isnot(None),
            func.json_type(LLMCallLog.conflict_flags_json).isnot(None),
        )
        .group_by(LLMCallLog.pipeline_type)
    ).all()
    for row in conflict_by_pipeline_rows:
        ptype = row.pipeline_type or "unknown"
        conflict_by_pipeline[ptype] = int(row.conflict_count or 0)

    by_pipeline = {}
    for row in by_pipeline_rows:
        ptype = row.pipeline_type or "unknown"
        calls = int(row.calls or 0)
        pipeline_conflicts = conflict_by_pipeline.get(ptype, 0)
        by_pipeline[ptype] = {
            "calls": calls,
            "cost_usd": round(float(row.cost or 0.0), 4),
            "tokens_in": int(row.tokens_in or 0),
            "tokens_out": int(row.tokens_out or 0),
            "conflict_rate_pct": round(pipeline_conflicts / calls * 100, 1) if calls > 0 else 0.0,
        }

    # Monthly cost
    monthly_cost = get_monthly_spend(db)

    return {
        "period_days": days,
        "total_calls": total_calls,
        "total_cost_usd": round(total_cost, 4),
        "total_tokens_in": total_tokens_in,
        "total_tokens_out": total_tokens_out,
        "avg_latency_ms": round(avg_latency, 1),
        "success_rate_pct": round(success_rate, 1),
        "conflict_rate_pct": conflict_rate,
        "by_pipeline": by_pipeline,
        "monthly_cost": monthly_cost,
    }


# ── LLM daily trend ──────────────────────────────────────────────────────────


def get_llm_trend(
    db: Session,
    days: int = 30,
) -> dict:
    """Daily LLM cost + token trend for sparkline chart.

    Returns:
        {
            "labels": ["2026-06-01", "2026-06-02", ...],
            "cost_usd": [1.2, 0.8, ...],
            "tokens_in": [50000, 30000, ...],
            "tokens_out": [8000, 5000, ...],
            "call_count": [5, 3, ...],
        }
    """
    cutoff = now() - timedelta(days=days)

    daily_rows = db.execute(
        select(
            func.date(LLMCallLog.created_at).label("day"),
            func.coalesce(func.sum(LLMCallLog.cost_usd), 0.0).label("cost"),
            func.coalesce(func.sum(LLMCallLog.tokens_in), 0).label("tokens_in"),
            func.coalesce(func.sum(LLMCallLog.tokens_out), 0).label("tokens_out"),
            func.count(LLMCallLog.id).label("calls"),
        )
        .where(LLMCallLog.created_at >= cutoff)
        .group_by(func.date(LLMCallLog.created_at))
        .order_by(func.date(LLMCallLog.created_at))
    ).all()

    return {
        "labels": [str(r.day) for r in daily_rows],
        "cost_usd": [round(float(r.cost or 0.0), 4) for r in daily_rows],
        "tokens_in": [int(r.tokens_in or 0) for r in daily_rows],
        "tokens_out": [int(r.tokens_out or 0) for r in daily_rows],
        "call_count": [int(r.calls or 0) for r in daily_rows],
    }


# ── Circuit breaker ──────────────────────────────────────────────────────────

CONFLICT_RATE_LIMIT_PCT: float = 20.0
"""If conflict rate exceeds this %, the circuit breaker blocks new runs."""

CIRCUIT_BREAKER_MIN_CALLS: int = 10
"""Minimum calls required before circuit breaker engages (avoid false trips)."""


def check_circuit_breaker(
    db: Session,
    pipeline_type: str,
    *,
    window_calls: int = 50,
) -> dict:
    """Check if a pipeline type should be blocked due to high conflict rate.

    Examines the last ``window_calls`` LLM calls for the given pipeline type.
    If the conflict rate exceeds CONFLICT_RATE_LIMIT_PCT and there are enough
    calls to be statistically meaningful, the breaker trips.

    Args:
        pipeline_type: e.g. "deep_research", "quality_screen"
        window_calls: number of recent calls to examine

    Returns:
        {
            "blocked": bool,
            "reason": str | None,
            "conflict_rate_pct": float,
            "recent_calls": int,
            "conflict_count": int,
        }
    """
    recent = (
        db.query(LLMCallLog)
        .filter(
            LLMCallLog.pipeline_type == pipeline_type,
            LLMCallLog.created_at >= now() - timedelta(days=7),
        )
        .order_by(LLMCallLog.created_at.desc())
        .limit(window_calls)
        .all()
    )

    total_calls = len(recent)
    if total_calls < CIRCUIT_BREAKER_MIN_CALLS:
        return {
            "blocked": False,
            "reason": None,
            "conflict_rate_pct": 0.0,
            "recent_calls": total_calls,
            "conflict_count": 0,
        }

    conflict_count = sum(
        1 for c in recent
        if c.conflict_flags_json
        and isinstance(c.conflict_flags_json, dict)
        and len(c.conflict_flags_json) > 0
    )
    conflict_rate = round(conflict_count / total_calls * 100, 1)
    blocked = conflict_rate >= CONFLICT_RATE_LIMIT_PCT

    reason = None
    if blocked:
        reason = (
            f"Circuit breaker tripped for {pipeline_type}: "
            f"conflict_rate={conflict_rate}% >= {CONFLICT_RATE_LIMIT_PCT}% "
            f"({conflict_count}/{total_calls} recent calls)"
        )

    return {
        "blocked": blocked,
        "reason": reason,
        "conflict_rate_pct": conflict_rate,
        "recent_calls": total_calls,
        "conflict_count": conflict_count,
    }
