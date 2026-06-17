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


def _serialize_draft(d, qiu_score: int | None = None, stock_name: str | None = None) -> dict:
    return {
        "id": d.id,
        "plan_id": d.plan_id,
        "code": d.code,
        "stock_name": stock_name,
        "side": d.side,
        "status": d.status,
        "step_kind": d.step_kind,
        "step_index": d.step_index,
        "add_pct": d.add_pct,
        "reduce_pct_of_position": d.reduce_pct_of_position,
        "suggested_quantity": getattr(d, "suggested_quantity", None),
        "qiu_score": qiu_score,
        "reason": d.reason,
        "source": getattr(d, "source", None),
        "triggered_at": str(d.triggered_at) if d.triggered_at else None,
    }


def _serialize_drafts_ranked(db: Session) -> list[dict]:
    """重审 #6 (2026-06-13): drafts 按 Qiu 评分 desc 排序展示。

    30-100 draft/天流入时,高分机会排前面,用户自选 Top N 深审。
    Qiu 评分取自 Stock.qiu_score (0-3);查不到的股票按 0 处理。
    2026-06-13 验收补充: 同时返回 stock_name 供前端表格显示。
    """
    from app.models.stock import Stock
    pending = draft_service.list_pending(db)
    if not pending:
        return []
    codes = {d.code for d in pending}
    stocks = db.query(Stock).filter(Stock.code.in_(codes)).all()
    score_map: dict[str, int] = {s.code: s.qiu_score or 0 for s in stocks}
    name_map: dict[str, str] = {s.code: s.name for s in stocks if s.name}
    ranked = sorted(
        pending,
        key=lambda d: (score_map.get(d.code, 0), d.triggered_at),
        reverse=True,
    )
    return [
        _serialize_draft(d, score_map.get(d.code, 0), name_map.get(d.code))
        for d in ranked
    ]


def _serialize_plan(p) -> dict:
    """Serialize a plan for cockpit display, including last run feedback.

    Includes G1/G2 fields (cycle_buy_max, disable_midstream_filter) and
    PlanRunResult feedback from last_run_summary (filtered_midstream_non_leader,
    cycle_buy_blocked, cycle_unavailable_skipped, cycle_position).
    """
    import json
    summary: dict | None = None
    if p.last_run_summary:
        try:
            summary = json.loads(p.last_run_summary)
        except (json.JSONDecodeError, TypeError):
            summary = None
    return {
        "id": p.id,
        "slug": p.slug,
        "name": p.name,
        "status": p.status,
        "description": p.description,
        "is_builtin": p.is_builtin,
        "cycle_buy_max": p.cycle_buy_max,
        "disable_midstream_filter": p.disable_midstream_filter,
        "last_run_at": p.last_run_at.isoformat() if p.last_run_at else None,
        "last_run_summary": summary,
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
        lambda: _serialize_drafts_ranked(db),
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
    # D4 (2026-06-17 invest-alignment): invest2 §7 平方差魔咒实时指标
    from app.services.portfolio_risk_service import compute_portfolio_risk
    portfolio_risk = _safe(
        "portfolio_risk",
        lambda: compute_portfolio_risk(db).to_dict(),
        {"has_holdings": False, "holdings_count": 0, "window_days": 0},
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
        "portfolio_risk": portfolio_risk,
        "serenity_summary": _get_latest_serenity_summary(db),
        "serenity_monthly_spend_cny": _get_monthly_serenity_spend(db),
        "errors": errors,
    }


def _get_monthly_serenity_spend(db: Session) -> dict | None:
    """Q8 ship checklist: current-month GLM token spend (CNY estimate)."""
    from datetime import datetime
    from sqlalchemy import func

    from app.core.research_config import COST_PER_1K_TOKENS_CNY
    from app.models.research_run import ResearchRun

    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    row = db.query(
        func.sum(ResearchRun.llm_token_input + ResearchRun.llm_token_output),
        func.count(ResearchRun.id),
    ).filter(
        ResearchRun.status == "completed",
        ResearchRun.started_at >= month_start,
    ).first()

    total_tokens, run_count = row if row else (0, 0)
    spend = ((total_tokens or 0) / 1000) * COST_PER_1K_TOKENS_CNY

    # Skip payload entirely if no runs this month (don't clutter cockpit)
    if not run_count:
        return None

    from app.config import settings
    budget = settings.SERENITY_MONTHLY_BUDGET_CNY
    return {
        "month": now.strftime("%Y-%m"),
        "spend_cny": round(spend, 2),
        "budget_cny": budget,
        "remaining_cny": round(max(0, budget - spend), 2),
        "run_count": run_count,
        "over_budget": spend > budget,
    }


def _get_latest_serenity_summary(db: Session) -> dict | None:
    """Q7 D: Cockpit "今日 serenity" 摘要卡片数据源。

    返回最近一次 status='completed' 的 ResearchRun + Top 3 ranked companies。
    若无完成 Run,返回 None (前端不显示卡片)。
    """
    from app.models.research_company_ranking import ResearchCompanyRanking
    from app.models.research_run import ResearchRun
    from app.models.research_theme import ResearchTheme

    latest_run = (
        db.query(ResearchRun, ResearchTheme)
        .join(ResearchTheme, ResearchRun.research_theme_id == ResearchTheme.id)
        .filter(
            ResearchRun.status == "completed",
            ResearchTheme.status == "active",
        )
        .order_by(ResearchRun.started_at.desc())
        .first()
    )
    if not latest_run:
        return None
    run, theme = latest_run

    top_rankings = (
        db.query(ResearchCompanyRanking)
        .filter(ResearchCompanyRanking.research_run_id == run.id)
        .order_by(ResearchCompanyRanking.rank)
        .limit(3)
        .all()
    )

    system_change = run.system_change_md or ""
    if len(system_change) > 200:
        system_change = system_change[:197] + "..."

    return {
        "theme_id": theme.id,
        "theme_name": theme.name,
        "run_id": run.id,
        "started_at": _iso(run.started_at),
        "system_change_excerpt": system_change,
        "token_input": run.llm_token_input,
        "token_output": run.llm_token_output,
        "search_count": run.llm_search_count,
        "top_rankings": [
            {
                "rank": r.rank,
                "stock_code": r.stock_code,
                "constrains_what": r.constrains_what,
                "main_risk_md": r.main_risk_md[:120] if r.main_risk_md else "",
            }
            for r in top_rankings
        ],
    }


def _iso(dt) -> str:
    from datetime import timezone
    if dt is None:
        return ""
    if hasattr(dt, "tzinfo") and dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt.isoformat()


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


