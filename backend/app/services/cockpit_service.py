"""Cockpit aggregator — one query → one DTO for the main dashboard.

Keeps the frontend "dumb": no client-side stitching across endpoints.
Heavy lifting (positions, weights, weighted DYR) is delegated to services
that already exist.

Failure isolation: each section is wrapped in try/except so a single
broken data source (e.g. Lixinger down for market indices) doesn't take
down the whole cockpit. Errors surface as `errors` field in the payload.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from sqlalchemy.orm import Session

from app.core.observability import get_logger, track_lifecycle
from app.models.alert import AlertEvent
from app.services import (
    alert_service,
    cashflow_service,
    draft_service,
    holding_service,
    plan_service,
    rebalance_service,
    theme_service,
)
from app.services.cycle_assessment_service import assess_cycle

logger = get_logger(__name__)

# Cache for expensive rebalance suggestions (TTL 1 hour)
_rebalance_cache: tuple[float, list[dict]] | None = None
_rebalance_cache_lock = threading.Lock()
_REBALANCE_CACHE_TTL = 3600.0


def _safe(name: str, fn, default, errors: list[str]):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        logger.exception("cockpit section %s failed", name)
        errors.append(f"{name}: {exc.__class__.__name__}: {exc}")
        return default


def _serialize_cashflow(m) -> dict:
    return {
        "annual_expense": m.annual_expense,
        "goal_multiple": m.goal_multiple,
        "target_annual_cashflow": m.target_annual_cashflow,
        "weighted_dyr": m.weighted_dyr,
        "annual_passive_cashflow": m.annual_passive_cashflow,
        "goal_progress": m.goal_progress,
        "total_portfolio_value": m.total_portfolio_value,
        "currency": m.currency,
    }


def _serialize_draft(d) -> dict:
    return {
        "id": d.id,
        "plan_id": d.plan_id,
        "code": d.code,
        "side": d.side,
        "status": d.status,
        "step_kind": d.step_kind,
        "step_index": d.step_index,
        "add_pct": d.add_pct,
        "reduce_pct_of_position": d.reduce_pct_of_position,
        "suggested_quantity": getattr(d, "suggested_quantity", None),
        "reason": d.reason,
        "source": getattr(d, "source", None),
        "triggered_at": str(d.triggered_at) if d.triggered_at else None,
    }


def _serialize_plan(p) -> dict:
    return {
        "id": p.id,
        "slug": p.slug,
        "name": p.name,
        "status": p.status,
        "description": p.description,
        "is_builtin": p.is_builtin,
    }


def _serialize_alert(ev: AlertEvent) -> dict:
    return {
        "id": ev.id,
        "rule_id": ev.rule_id,
        "stock_code": ev.stock_code,
        "level": ev.level,
        "message": ev.message,
        "triggered_at": str(ev.triggered_at) if ev.triggered_at else None,
    }


@track_lifecycle(span_name="cockpit.build")
def build(db: Session) -> dict:
    """Assemble the cockpit DTO.

    Sections:
      - cashflow:  navigation (target / weighted DYR / progress)
      - drafts:    pending order drafts (BUY/SELL todo)
      - holdings:  enriched active position list (already paginated)
      - quadrant:  four-quadrant breakdown (pie chart data)
      - alerts:    unacked alert events (top 20)
      - plans:     active plan summary
      - errors:    list of section names that fell back to defaults
    """
    errors: list[str] = []

    cashflow = _safe(
        "cashflow",
        lambda: _serialize_cashflow(cashflow_service.compute(db)),
        {},
        errors,
    )
    drafts = _safe(
        "drafts",
        lambda: [_serialize_draft(d) for d in draft_service.list_pending(db)],
        [],
        errors,
    )
    holdings_summary = _safe(
        "holdings",
        lambda: holding_service.get_portfolio_summary(db),
        {"holdings": [], "warnings": []},
        errors,
    )
    quadrant = _safe(
        "quadrant",
        lambda: cashflow_service.quadrant_breakdown(db),
        [],
        errors,
    )
    alerts = _safe(
        "alerts",
        lambda: [
            _serialize_alert(ev)
            for ev in alert_service.list_events(db, acked=False, limit=20)
        ],
        [],
        errors,
    )
    plans = _safe(
        "plans",
        lambda: [_serialize_plan(p) for p in plan_service.list_active(db)],
        [],
        errors,
    )
    theme_exposure = _safe(
        "theme_exposure",
        lambda: theme_service.get_theme_exposure(db),
        [],
        errors,
    )
    rebalance_suggestions = _safe(
        "rebalance_suggestions",
        lambda: _get_rebalance_suggestions(db),
        [],
        errors,
    )
    cycle = _safe(
        "cycle",
        lambda: assess_cycle(db).model_dump(),
        {},
        errors,
    )
    from app.services.dividend_projector_service import project as project_dividends
    dividend_projection = _safe(
        "dividend_projection",
        lambda: project_dividends(db).model_dump(),
        {},
        errors,
    )
    from app.services.thesis_monitor_service import check_held_stocks
    thesis_alerts = _safe(
        "thesis_alerts",
        lambda: [a.model_dump() for a in check_held_stocks(db)],
        [],
        errors,
    )

    holdings_payload: list[dict[str, Any]] = []
    holdings_warnings: list[str] = []
    if isinstance(holdings_summary, dict):
        holdings_payload = holdings_summary.get("holdings") or []
        holdings_warnings = holdings_summary.get("warnings") or []

    return {
        "as_of": _now_iso(),
        "cashflow": cashflow,
        "drafts": drafts,
        "holdings": {
            "items": holdings_payload,
            "warnings": holdings_warnings,
            "summary": (
                holdings_summary.get("summary")
                if isinstance(holdings_summary, dict)
                else None
            ),
        },
        "quadrant": quadrant,
        "alerts": {
            "items": alerts,
            "unacked_count": len(alerts),
        },
        "plans": plans,
        "theme_exposure": theme_exposure,
        "rebalance_suggestions": rebalance_suggestions,
        "cycle": cycle,
        "dividend_projection": dividend_projection,
        "thesis_alerts": thesis_alerts,
        "errors": errors,
    }


def _get_rebalance_suggestions(db: Session) -> list[dict]:
    """Compute rebalance suggestions with a 1-hour TTL cache."""
    global _rebalance_cache
    now = time.monotonic()
    with _rebalance_cache_lock:
        if _rebalance_cache is not None:
            ts, data = _rebalance_cache
            if now - ts < _REBALANCE_CACHE_TTL:
                return data
        suggestions = [
            s.model_dump()
            for s in rebalance_service.compute_rebalancing_suggestions(db, drift_threshold=0.05)
        ]
        _rebalance_cache = (now, suggestions)
    return suggestions


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


