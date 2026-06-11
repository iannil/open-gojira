"""Cashflow-goal derived metrics.

Combines the singleton `cashflow_goal` (annual_expense × goal_multiple) with
the live portfolio summary to produce the autopilot's "navigation" numbers:
weighted DYR, annual passive cashflow, and progress toward the target.

Pure read/derive — does not mutate state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.services import cashflow_goal_service, holding_service


@dataclass
class CashflowMetrics:
    annual_expense: float
    goal_multiple: float
    target_annual_cashflow: float

    weighted_dyr: Optional[float]
    """组合加权股息率 (decimal, 0.046 == 4.6%)."""

    annual_passive_cashflow: float
    """total_portfolio_value × weighted_dyr (0 when weighted_dyr is None)."""

    goal_progress: Optional[float]
    """annual_passive_cashflow / target_annual_cashflow (None when target=0)."""

    total_portfolio_value: float
    """equity + cash_reserve — matches holdings summary's grand_total."""

    currency: str


def compute(db: Session) -> CashflowMetrics:
    goal = cashflow_goal_service.get_or_create(db)
    summary = holding_service.get_portfolio_summary(db)

    equity = float(summary.get("total_value") or 0.0)
    cash_reserve = float(summary.get("cash_reserve") or 0.0)
    total = equity + cash_reserve

    weighted_dyr = summary.get("portfolio_weighted_dyr")
    if isinstance(weighted_dyr, (int, float)):
        weighted_dyr = float(weighted_dyr)
    else:
        weighted_dyr = None

    annual_passive_cf = (total * weighted_dyr) if weighted_dyr is not None else 0.0

    target = cashflow_goal_service.target_annual_cashflow(goal)
    goal_progress = (annual_passive_cf / target) if target > 0 else None

    return CashflowMetrics(
        annual_expense=float(goal.annual_expense),
        goal_multiple=float(goal.goal_multiple),
        target_annual_cashflow=target,
        weighted_dyr=weighted_dyr,
        annual_passive_cashflow=annual_passive_cf,
        goal_progress=goal_progress,
        total_portfolio_value=total,
        currency=goal.currency,
    )


def quadrant_breakdown(db: Session) -> list[dict]:
    """Group active holdings by stocks.quadrant; weights as percentage of equity.

    Returns one dict per non-zero quadrant bucket:
    `{quadrant, value, weight_pct, count, stock_codes}`. Unlabeled holdings
    fall into "unlabeled" so blind spots stay visible.
    """
    from app.models.stock import Stock  # avoid model-cycle warning

    summary = holding_service.get_portfolio_summary(db)
    holdings = summary.get("holdings") or []
    total_value = float(summary.get("total_value") or 0.0)
    if not holdings or total_value <= 0:
        return []

    codes = [h["stock_code"] for h in holdings]
    quadrant_map: dict[str, Optional[str]] = {}
    if codes:
        for s in db.query(Stock).filter(Stock.code.in_(codes)).all():
            quadrant_map[s.code] = s.quadrant

    buckets: dict[str, dict] = {}
    for h in holdings:
        value = (
            h["current_value"]
            if h.get("current_value") is not None
            else h["buy_price"] * h["quantity"]
        )
        label = quadrant_map.get(h["stock_code"]) or "unlabeled"
        bucket = buckets.setdefault(
            label,
            {"quadrant": label, "value": 0.0, "count": 0, "stock_codes": []},
        )
        bucket["value"] += value
        bucket["count"] += 1
        bucket["stock_codes"].append(h["stock_code"])

    result = []
    for b in buckets.values():
        b["weight_pct"] = b["value"] / total_value * 100
        result.append(b)
    result.sort(key=lambda x: x["weight_pct"], reverse=True)
    return result
