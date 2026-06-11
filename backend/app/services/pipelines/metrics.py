"""Metrics collector — API usage tracking and sync performance metrics."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import case, func as sa_func
from sqlalchemy.orm import Session

from app.core.datetime_utils import utcnow
from app.models.pipeline import ApiUsageLog

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Records and queries API usage metrics."""

    @staticmethod
    def record(
        db: Session,
        endpoint: str,
        duration_ms: int | None = None,
        stock_code: str | None = None,
        cached: bool = False,
        error: str | None = None,
    ) -> None:
        log = ApiUsageLog(
            endpoint=endpoint,
            stock_code=stock_code,
            duration_ms=duration_ms,
            cached=1 if cached else 0,
            error=error[:2000] if error else None,
        )
        db.add(log)
        db.commit()

    @staticmethod
    def get_daily_summary(db: Session, target_date: date | None = None) -> dict:
        d = target_date or date.today()
        rows = (
            db.query(
                ApiUsageLog.endpoint,
                sa_func.count(ApiUsageLog.id).label("calls"),
                sa_func.sum(ApiUsageLog.cached).label("cached_hits"),
                sa_func.sum(
                    case((ApiUsageLog.error.isnot(None), 1), else_=0)
                ).label("errors"),
                sa_func.avg(ApiUsageLog.duration_ms).label("avg_ms"),
            )
            .filter(
                sa_func.date(ApiUsageLog.called_at) == d
            )
            .group_by(ApiUsageLog.endpoint)
            .all()
        )
        endpoint_stats = []
        total_calls = 0
        total_cached = 0
        total_errors = 0
        for r in rows:
            calls = r.calls or 0
            cached = r.cached_hits or 0
            errors = r.errors or 0
            total_calls += calls
            total_cached += cached
            total_errors += errors
            endpoint_stats.append({
                "endpoint": r.endpoint,
                "calls": calls,
                "cached_hits": cached,
                "errors": errors,
                "avg_ms": round(r.avg_ms, 1) if r.avg_ms else None,
            })
        return {
            "date": str(d),
            "total_calls": total_calls,
            "total_cached_hits": total_cached,
            "total_errors": total_errors,
            "cache_hit_rate": round(total_cached / max(1, total_calls) * 100, 1),
            "endpoints": endpoint_stats,
        }

    @staticmethod
    def get_monthly_summary(db: Session, year: int | None = None, month: int | None = None) -> dict:
        now = utcnow()
        y = year or now.year
        m = month or now.month
        start = date(y, m, 1)
        if m == 12:
            end = date(y + 1, 1, 1)
        else:
            end = date(y, m + 1, 1)

        row = (
            db.query(
                sa_func.count(ApiUsageLog.id).label("calls"),
                sa_func.sum(ApiUsageLog.cached).label("cached"),
                sa_func.sum(
                    case((ApiUsageLog.error.isnot(None), 1), else_=0)
                ).label("errors"),
            )
            .filter(
                ApiUsageLog.called_at >= start,
                ApiUsageLog.called_at < end,
            )
            .first()
        )
        calls = row.calls or 0
        return {
            "year": y,
            "month": m,
            "total_calls": calls,
            "total_cached": row.cached or 0,
            "total_errors": row.errors or 0,
            "budget": 10000,
            "budget_used_pct": round(calls / 10000 * 100, 1),
        }

    @staticmethod
    def get_trend(db: Session, days: int = 30) -> list[dict]:
        """Daily call counts for the last N days."""
        since = date.today() - timedelta(days=days)
        rows = (
            db.query(
                sa_func.date(ApiUsageLog.called_at).label("d"),
                sa_func.count(ApiUsageLog.id).label("calls"),
                sa_func.sum(ApiUsageLog.cached).label("cached"),
            )
            .filter(sa_func.date(ApiUsageLog.called_at) >= since)
            .group_by(sa_func.date(ApiUsageLog.called_at))
            .order_by(sa_func.date(ApiUsageLog.called_at))
            .all()
        )
        return [
            {"date": str(r.d), "calls": r.calls, "cached": r.cached or 0}
            for r in rows
        ]
