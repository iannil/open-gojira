"""Cockpit aggregator — v2 信号优先 dashboard (decision 19).

One query → one DTO for the main dashboard, over v2-valid sources only:
  - drafts:          pending order drafts (BUY/SELL todo)          [顶部待办信号]
  - portfolio:       holdings + summary                            [中部持仓概览]
  - pipeline_counts: stock_lifecycle state counts (watchlist/      [底部 候选+观察池]
                     candidate/researched/...)
  - alerts:          unresolved in-app SystemAlerts + critical N   [应用内通知]
  - recent_reports:  latest research reports (BUY/HOLD/PASS + 评分)  [信号 + 报告阅读]

Failure isolation: each section is wrapped in _safe so one broken source does
not take down the whole cockpit; failures surface in the `errors` field.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.datetime_utils import now
from app.core.observability import get_logger
from app.models.research_report import ResearchReport
from app.services import draft_service, holding_service, lifecycle_service
from app.services import system_alert_service

logger = get_logger(__name__)


def _safe(name: str, fn, default, errors: list[str]):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        logger.exception("cockpit section %s failed", name)
        errors.append(f"{name}: {exc.__class__.__name__}: {exc}")
        return default


def _serialize_draft(d) -> dict:
    return {
        "id": d.id,
        "code": d.code,
        "side": d.side,
        "status": d.status,
        "step_kind": d.step_kind,
        "step_index": d.step_index,
        "add_pct": d.add_pct,
        "reduce_pct_of_position": d.reduce_pct_of_position,
        "suggested_quantity": d.suggested_quantity,
        "reason": d.reason,
        "source": d.source,
        "triggered_at": _iso(d.triggered_at),
    }


def _serialize_alert(a) -> dict:
    return {
        "id": a.id,
        "severity": a.severity,
        "category": a.category,
        "message": a.message,
        "created_at": _iso(a.created_at),
    }


def _serialize_report(r: ResearchReport) -> dict:
    return {
        "id": r.id,
        "stock_code": r.stock_code,
        "pipeline_type": r.pipeline_type,
        "overall_score": r.overall_score,
        "recommendation": r.recommendation,
        "evidence_grade": r.evidence_grade,
        "status": r.status,
        "created_at": _iso(r.created_at),
    }


def _recent_reports(db: Session, limit: int = 10) -> list[ResearchReport]:
    return list(
        db.query(ResearchReport)
        .order_by(desc(ResearchReport.created_at))
        .limit(limit)
        .all()
    )


def build(db: Session) -> dict:
    """Assemble the v2 信号优先 cockpit DTO (decision 19)."""
    errors: list[str] = []

    drafts = _safe(
        "drafts",
        lambda: [_serialize_draft(d) for d in draft_service.list_pending(db)],
        [],
        errors,
    )
    portfolio = _safe(
        "portfolio",
        lambda: holding_service.get_portfolio_summary(db),
        {"holdings": [], "summary": None},
        errors,
    )
    pipeline_counts = _safe(
        "pipeline_counts",
        lambda: lifecycle_service.count_by_state(db),
        {},
        errors,
    )
    alerts = _safe(
        "alerts",
        lambda: [
            _serialize_alert(a)
            for a in system_alert_service.list_unresolved(db, limit=20)
        ],
        [],
        errors,
    )
    critical_count = _safe(
        "critical_count",
        lambda: system_alert_service.get_critical_unresolved_count(db),
        0,
        errors,
    )
    recent_reports = _safe(
        "recent_reports",
        lambda: [_serialize_report(r) for r in _recent_reports(db, limit=10)],
        [],
        errors,
    )

    portfolio = portfolio if isinstance(portfolio, dict) else {}
    return {
        "as_of": _iso(now()),
        # 顶部：待办信号
        "drafts": drafts,
        "drafts_pending_count": len(drafts),
        # 中部：持仓概览（summary = 组合指标，holdings = 明细）
        "portfolio": {
            "summary": {k: v for k, v in portfolio.items() if k != "holdings"},
            "holdings": portfolio.get("holdings") or [],
        },
        # 底部：候选池 + 观察池（lifecycle 状态计数）
        "pipeline_counts": pipeline_counts,
        # 应用内通知
        "alerts": {
            "items": alerts,
            "critical_count": critical_count,
        },
        # 信号 + 报告阅读
        "recent_reports": recent_reports,
        "errors": errors,
    }


def _iso(dt) -> str | None:
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is not None:
        dt = dt.replace(tzinfo=None)
    return dt.isoformat()
