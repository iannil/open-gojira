"""Periodic review service — quarterly and annual portfolio review automation.

Implements invest3's "five-layer pyramid" requirement for structured self-assessment.
"""

import logging
from datetime import date

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.cashflow_goal import CashflowGoal
from app.models.dividend import DividendRecord
from app.models.draft import Draft
from app.models.holding import Holding
from app.models.plan import Plan
from app.models.stock import Stock
from app.models.valuation import ValuationSnapshot

logger = logging.getLogger(__name__)


def quarterly_review(db: Session, year: int, quarter: int) -> dict:
    """Generate quarterly review data.

    Quarter must be 1-4. Returns plan success rate, theme alignment,
    discipline score, and thesis variable drift summary.
    """
    current_year = date.today().year
    if not (2000 <= year <= current_year + 1):
        return {"error": f"year must be between 2000 and {current_year + 1}"}
    if quarter not in (1, 2, 3, 4):
        return {"error": "quarter must be 1-4"}

    q_start = date(year, (quarter - 1) * 3 + 1, 1)
    if quarter < 4:
        q_end = date(year, quarter * 3 + 1, 1)
    else:
        q_end = date(year + 1, 1, 1)

    # Plan success rate
    plans_completed = db.query(Plan).filter(
        Plan.status == "completed",
        Plan.updated_at >= q_start,
        Plan.updated_at < q_end,
    ).count()
    plans_invalidated = db.query(Plan).filter(
        Plan.status == "invalidated",
        Plan.updated_at >= q_start,
        Plan.updated_at < q_end,
    ).count()
    plans_expired = db.query(Plan).filter(
        Plan.status == "expired",
        Plan.updated_at >= q_start,
        Plan.updated_at < q_end,
    ).count()
    total_resolved = plans_completed + plans_invalidated + plans_expired
    plan_success_rate = (plans_completed / total_resolved * 100) if total_resolved > 0 else None

    # Drafts executed vs cancelled
    drafts_executed = db.query(Draft).filter(
        Draft.status == "executed",
        Draft.executed_at >= q_start,
        Draft.executed_at < q_end,
    ).count()
    drafts_cancelled = db.query(Draft).filter(
        Draft.status == "cancelled",
        Draft.triggered_at >= q_start,
        Draft.triggered_at < q_end,
    ).count()

    # Discipline score: % of drafts with discipline_checklist in audit log
    discipline_logs = db.query(AuditLog).filter(
        AuditLog.event == "executed",
        AuditLog.entity_type == "draft",
        AuditLog.created_at >= q_start,
        AuditLog.created_at < q_end,
    ).all()
    discipline_total = len(discipline_logs)
    discipline_with_checklist = sum(
        1 for l in discipline_logs
        if l.payload and "discipline_checklist" in (l.payload or {})
    )

    # Theme alignment
    held_stocks = db.query(Holding).filter(Holding.sell_date.is_(None)).all()
    held_codes = [h.stock_code for h in held_stocks]
    stocks_with_theme = db.query(Stock).filter(
        Stock.code.in_(held_codes),
        Stock.security_theme.isnot(None),
    ).count() if held_codes else 0
    theme_alignment = (stocks_with_theme / len(held_codes) * 100) if held_codes else 0

    # Tier distribution
    stocks_with_tier = db.query(Stock).filter(
        Stock.code.in_(held_codes),
        Stock.tier.isnot(None),
    ).all() if held_codes else []
    tier_dist = {}
    for s in stocks_with_tier:
        tier_dist[s.tier] = tier_dist.get(s.tier, 0) + 1

    return {
        "period": f"{year}Q{quarter}",
        "plan_success_rate": round(plan_success_rate, 1) if plan_success_rate is not None else None,
        "plans_completed": plans_completed,
        "plans_invalidated": plans_invalidated,
        "plans_expired": plans_expired,
        "drafts_executed": drafts_executed,
        "drafts_cancelled": drafts_cancelled,
        "discipline_score": round(discipline_with_checklist / discipline_total * 100, 1) if discipline_total > 0 else None,
        "discipline_with_checklist": discipline_with_checklist,
        "discipline_total": discipline_total,
        "theme_alignment_pct": round(theme_alignment, 1),
        "tier_distribution": tier_dist,
        "holdings_count": len(held_stocks),
    }


def annual_review(db: Session, year: int) -> dict:
    """Generate annual review data.

    Extends quarterly data with cashflow goal progress, portfolio volatility,
    dividend income vs projection, and tier performance.
    """
    year_start = date(year, 1, 1)
    year_end = date(year + 1, 1, 1)

    # Aggregate all 4 quarters
    quarters = [quarterly_review(db, year, q) for q in (1, 2, 3, 4)]

    total_executed = sum(q["drafts_executed"] for q in quarters)
    total_cancelled = sum(q["drafts_cancelled"] for q in quarters)

    # Cashflow goal progress
    goal = db.query(CashflowGoal).filter(CashflowGoal.id == 1).first()
    goal_progress = None
    if goal and goal.annual_expense:
        held_stocks = db.query(Holding).filter(Holding.sell_date.is_(None)).all()
        total_value = sum(h.buy_price * h.quantity for h in held_stocks)
        # Rough estimate: weighted DYR × portfolio value / annual expense
        dyrs = []
        for h in held_stocks:
            snap = db.query(ValuationSnapshot).filter(
                ValuationSnapshot.stock_code == h.stock_code
            ).order_by(ValuationSnapshot.date.desc()).first()
            if snap and snap.dividend_yield:
                dyrs.append((h.buy_price * h.quantity, float(snap.dividend_yield)))
        weighted_dyr = sum(v * d for v, d in dyrs) / sum(v for v, d in dyrs) if dyrs else 0
        annual_income = total_value * weighted_dyr
        goal_progress = round(annual_income / goal.annual_expense * 100, 1) if goal.annual_expense else None

    # Dividend income
    dividends = db.query(DividendRecord).filter(
        DividendRecord.ex_date >= year_start,
        DividendRecord.ex_date < year_end,
    ).all()
    dividend_income = sum((d.amount_per_share or 0) for d in dividends)

    return {
        "period": str(year),
        "quarters": quarters,
        "total_executed": total_executed,
        "total_cancelled": total_cancelled,
        "goal_progress_pct": goal_progress,
        "dividend_records_count": len(dividends),
        "dividend_income_estimate": round(dividend_income, 2),
        "holdings_count": sum(q["holdings_count"] for q in quarters[:1]),  # latest quarter
    }
