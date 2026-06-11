"""Dividend projection service — 未来12月股息收入预测.

Answers: "未来12个月我能收多少股息？" and "离现金流目标还差多少？"
Aligns with invest3 "高股息是底" + cashflow goal "被动现金流自由".
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from collections import defaultdict

from pydantic import BaseModel, field_serializer
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.cashflow_goal import CashflowGoal
from app.models.dividend import DividendRecord
from app.models.holding import Holding
from app.models.stock import Stock
from app.models.valuation import ValuationSnapshot

logger = logging.getLogger(__name__)


class HoldingDividendForecast(BaseModel):
    code: str
    name: str
    quantity: int
    expected_per_share: float
    expected_total: float
    expected_ex_month: int | None
    yield_pct: float | None

    @field_serializer("expected_per_share")
    def _round_per_share(self, v: float) -> float:
        return round(v, 4)

    @field_serializer("expected_total")
    def _round_total(self, v: float) -> float:
        return round(v, 2)

    @field_serializer("yield_pct")
    def _round_yield(self, v: float | None) -> float | None:
        return round(v, 4) if v else None


class DividendProjection(BaseModel):
    next_12m_expected: float
    by_holding: list[HoldingDividendForecast]
    annual_passive_target: float | None
    dividend_gap: float | None
    dividend_coverage: float | None
    trailing_12m_actual: float
    projection_basis: str

    @field_serializer("next_12m_expected", "trailing_12m_actual")
    def _round2(self, v: float) -> float:
        return round(v, 2)

    @field_serializer("annual_passive_target", "dividend_gap")
    def _round2_opt(self, v: float | None) -> float | None:
        return round(v, 2) if v is not None else None

    @field_serializer("dividend_coverage")
    def _round4_opt(self, v: float | None) -> float | None:
        return round(v, 4) if v is not None else None


def _latest_dyr(db: Session, code: str) -> float | None:
    row = db.execute(
        select(ValuationSnapshot.dividend_yield)
        .where(ValuationSnapshot.stock_code == code)
        .order_by(ValuationSnapshot.date.desc())
        .limit(1)
    ).scalar_one_or_none()
    return float(row) if row else None


def _historical_ex_months(db: Session, code: str) -> list[int]:
    rows = db.execute(
        select(DividendRecord.ex_date)
        .where(DividendRecord.stock_code == code)
        .order_by(DividendRecord.ex_date.desc())
        .limit(5)
    ).scalars().all()
    return [r.month for r in rows if r]


def _historical_avg_per_share(db: Session, code: str, years: int = 3) -> float | None:
    cutoff = date.today() - timedelta(days=years * 365)
    row = db.execute(
        select(func.avg(DividendRecord.amount_per_share))
        .where(
            DividendRecord.stock_code == code,
            DividendRecord.ex_date >= cutoff,
        )
    ).scalar_one_or_none()
    return float(row) if row else None


def _trailing_12m_actual(db: Session) -> float:
    cutoff = date.today() - timedelta(days=365)
    row = db.execute(
        select(func.sum(DividendRecord.total_received))
        .where(DividendRecord.ex_date >= cutoff)
    ).scalar_one_or_none()
    return float(row) if row else 0.0


def project(db: Session) -> DividendProjection:
    """Project dividend income for the next 12 months based on current holdings."""
    holdings = list(
        db.execute(
            select(Holding).where(Holding.sell_date.is_(None))
        ).scalars().all()
    )

    if not holdings:
        return DividendProjection(
            next_12m_expected=0.0,
            by_holding=[],
            annual_passive_target=None,
            dividend_gap=None,
            dividend_coverage=None,
            trailing_12m_actual=_trailing_12m_actual(db),
            projection_basis="no holdings",
        )

    by_holding: list[HoldingDividendForecast] = []
    total_expected = 0.0

    for h in holdings:
        stock = db.get(Stock, h.stock_code)
        name = stock.name if stock else h.stock_code

        # Estimate next dividend per share:
        # 1. Historical average (most reliable)
        # 2. Fallback: current yield * latest price
        avg_per_share = _historical_avg_per_share(db, h.stock_code)
        dyr = _latest_dyr(db, h.stock_code)

        if avg_per_share and avg_per_share > 0:
            expected_per_share = avg_per_share
            basis_detail = "3年平均"
        elif dyr and dyr > 0:
            price = h.buy_price
            expected_per_share = dyr * price
            basis_detail = "当前股息率×成本价"
        else:
            continue

        expected_total = expected_per_share * h.quantity
        total_expected += expected_total

        ex_months = _historical_ex_months(db, h.stock_code)
        expected_ex_month = ex_months[0] if ex_months else None

        by_holding.append(HoldingDividendForecast(
            code=h.stock_code,
            name=name,
            quantity=h.quantity,
            expected_per_share=expected_per_share,
            expected_total=expected_total,
            expected_ex_month=expected_ex_month,
            yield_pct=dyr,
        ))

    # Compare against cashflow goal
    goal = db.execute(
        select(CashflowGoal).where(CashflowGoal.id == 1)
    ).scalar_one_or_none()

    annual_target = None
    gap = None
    coverage = None
    if goal:
        # target = annual_expense * goal_multiple
        annual_target = float(goal.annual_expense) * float(goal.goal_multiple)
        if annual_target > 0:
            gap = annual_target - total_expected
            coverage = total_expected / annual_target

    return DividendProjection(
        next_12m_expected=total_expected,
        by_holding=by_holding,
        annual_passive_target=annual_target,
        dividend_gap=gap,
        dividend_coverage=coverage,
        trailing_12m_actual=_trailing_12m_actual(db),
        projection_basis="历史分红均值 + 当前股息率",
    )
