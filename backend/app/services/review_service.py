"""Monthly review aggregator — autopilot's "事后一刀两断" view.

Reads the audit_log within a month window and computes:
- draft hit rate (executed / triggered)
- plan churn (created / invalidated / status transitions)
- holdings activity (created / sold)
- evaluator coverage (drafts emitted by stock_code)

Pure read; no mutation.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


@dataclass
class MonthWindow:
    year: int
    month: int
    start: datetime
    end: datetime           # exclusive
    label: str              # "2026-06"

    @classmethod
    def parse(cls, year_month: Optional[str]) -> "MonthWindow":
        """Accepts 'YYYY-MM' (default = current month in local time)."""
        if year_month:
            y, m = year_month.split("-", 1)
            year, month = int(y), int(m)
        else:
            today = date.today()
            year, month = today.year, today.month
        start = datetime(year, month, 1)
        if month == 12:
            end = datetime(year + 1, 1, 1)
        else:
            end = datetime(year, month + 1, 1)
        return cls(
            year=year,
            month=month,
            start=start,
            end=end,
            label=f"{year:04d}-{month:02d}",
        )

    def previous(self) -> "MonthWindow":
        first_prev = self.start - timedelta(days=1)
        return MonthWindow.parse(f"{first_prev.year:04d}-{first_prev.month:02d}")


@dataclass
class CycleSnapshot:
    """Current market cycle state at review time."""
    cycle_position: str
    pe_pct_10y: Optional[float]
    position_range: list[float]
    position_advice: str


@dataclass
class ThesisReviewAlert:
    """A thesis variable that is currently breached."""
    code: str
    stock_name: str
    variable_name: str
    current_value: Optional[float]
    threshold_type: str
    threshold_value: float
    message: str

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "stock_name": self.stock_name,
            "variable_name": self.variable_name,
            "current_value": self.current_value,
            "threshold_type": self.threshold_type,
            "threshold_value": self.threshold_value,
            "message": self.message,
        }


@dataclass
class ReviewSummary:
    month: str
    drafts_triggered: int = 0
    drafts_executed: int = 0
    drafts_cancelled: int = 0
    hit_rate: Optional[float] = None
    buy_drafts: int = 0
    sell_drafts: int = 0
    plans_created: int = 0
    plans_invalidated: int = 0
    plans_status_changed: int = 0
    holdings_created: int = 0
    holdings_sold: int = 0
    cashflow_goal_updates: int = 0
    by_stock: list[dict] = field(default_factory=list)
    """Top stocks by draft activity this month."""
    entries: list[dict] = field(default_factory=list)
    """Recent log entries inside the window (most recent first)."""
    cycle: Optional[CycleSnapshot] = None
    """Current market cycle position at review time."""
    thesis_alerts: list[ThesisReviewAlert] = field(default_factory=list)
    """Currently breached thesis variables for held stocks."""


def _entry_to_dict(row: AuditLog) -> dict:
    import json
    payload = None
    if row.payload:
        try:
            parsed = json.loads(row.payload)
            payload = parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            payload = None
    return {
        "id": row.id,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "event": row.event,
        "actor": row.actor,
        "stock_code": row.stock_code,
        "summary": row.summary,
        "payload": payload,
        "created_at": str(row.created_at) if row.created_at else None,
    }


def compute(
    db: Session,
    year_month: Optional[str] = None,
    *,
    entry_limit: int = 200,
) -> ReviewSummary:
    win = MonthWindow.parse(year_month)
    summary = ReviewSummary(month=win.label)

    rows = (
        db.execute(
            select(AuditLog).where(
                and_(
                    AuditLog.created_at >= win.start,
                    AuditLog.created_at < win.end,
                )
            )
        )
        .scalars()
        .all()
    )

    stock_counter: Counter[str] = Counter()

    for r in rows:
        if r.entity_type == "draft":
            if r.event == "triggered":
                summary.drafts_triggered += 1
                payload = _safe_payload(r.payload)
                if payload and payload.get("add_pct") is not None:
                    summary.buy_drafts += 1
                elif payload and payload.get("reduce_pct_of_position") is not None:
                    summary.sell_drafts += 1
                if r.stock_code:
                    stock_counter[r.stock_code] += 1
            elif r.event == "executed":
                summary.drafts_executed += 1
            elif r.event == "cancelled":
                summary.drafts_cancelled += 1
        elif r.entity_type == "plan":
            if r.event == "created":
                summary.plans_created += 1
            elif r.event == "invalidated":
                summary.plans_invalidated += 1
            elif r.event == "status_changed":
                summary.plans_status_changed += 1
        elif r.entity_type == "holding":
            if r.event == "created":
                summary.holdings_created += 1
            elif r.event == "sold":
                summary.holdings_sold += 1
        elif r.entity_type == "cashflow_goal":
            if r.event == "updated":
                summary.cashflow_goal_updates += 1

    if summary.drafts_triggered > 0:
        summary.hit_rate = summary.drafts_executed / summary.drafts_triggered

    summary.by_stock = [
        {"stock_code": code, "drafts_triggered": n}
        for code, n in stock_counter.most_common(10)
    ]

    # Enrich by_stock with business_pattern context (D3: 核心变量提示)
    # so the Review UI can prompt auditors to check each stock's core driver.
    if summary.by_stock:
        from app.models.business_pattern import BusinessPattern
        from app.models.stock import Stock
        codes = [item["stock_code"] for item in summary.by_stock]
        stock_rows = (
            db.query(Stock.code, Stock.business_pattern_id)
            .filter(Stock.code.in_(codes))
            .all()
        )
        code_to_pid = {row[0]: row[1] for row in stock_rows}
        pids = {pid for pid in code_to_pid.values() if pid is not None}
        patterns = (
            db.query(BusinessPattern)
            .filter(BusinessPattern.id.in_(pids))
            .all()
            if pids
            else []
        )
        pid_to_pattern = {p.id: p for p in patterns}
        for item in summary.by_stock:
            pid = code_to_pid.get(item["stock_code"])
            if pid is None:
                item["business_pattern_name"] = None
                item["first_principle_variable"] = None
                continue
            p = pid_to_pattern.get(pid)
            item["business_pattern_name"] = p.name if p else None
            item["first_principle_variable"] = (
                p.first_principle_variable if p else None
            )

    # Trim entries to most recent N for the timeline view
    rows_sorted = sorted(
        rows,
        key=lambda r: (r.created_at or datetime.min, r.id),
        reverse=True,
    )[:entry_limit]
    summary.entries = [_entry_to_dict(r) for r in rows_sorted]

    # ── Cycle snapshot (current state) ────────────────────────────────
    try:
        from app.services.cycle_assessment_service import assess_cycle
        ca = assess_cycle(db)
        summary.cycle = CycleSnapshot(
            cycle_position=ca.cycle_position,
            pe_pct_10y=ca.pe_pct_10y,
            position_range=[ca.position_min, ca.position_max],
            position_advice=ca.position_advice,
        )
    except Exception:
        import logging
        logging.getLogger(__name__).warning("Failed to compute cycle snapshot for review", exc_info=True)

    # ── Thesis variable alerts (current breaches) ─────────────────────
    try:
        from app.services.thesis_monitor_service import check_held_stocks
        for a in check_held_stocks(db):
            summary.thesis_alerts.append(ThesisReviewAlert(
                code=a.code,
                stock_name=a.stock_name,
                variable_name=a.variable_name,
                current_value=a.current_value,
                threshold_type=a.threshold_type,
                threshold_value=a.threshold_value,
                message=a.message,
            ))
    except Exception:
        import logging
        logging.getLogger(__name__).warning("Failed to compute thesis alerts for review", exc_info=True)

    return summary


def _safe_payload(raw: str | None) -> Optional[dict]:
    if not raw:
        return None
    import json
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None
