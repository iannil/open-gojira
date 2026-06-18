"""Dividend projection service — 未来12月股息收入预测.

Answers: "未来12个月我能收多少股息？" and "离现金流目标还差多少？"
Aligns with invest3 "高股息是底" + cashflow goal "被动现金流自由".
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

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
    """F17 (2026-06-18): 3-year average DPS, only counting years that
    actually paid a dividend.

    Used as fallback for forward_dyr when Lixinger trailing_12m_dyr is missing.

    Previous algorithm averaged all DPS values in the window including
    years where DPS=0 (经营困难期 / 财报亏损). This systematically
    underestimated forward_dyr for recovery stocks.

    Real-world impact (spike 2026-06-18):
      002170 芭田股份: old=0.168 → new=0.337 → forward_dyr 1.5% → 3.0%
      601398 工商银行: old=0.175 → new=0.245 → forward_dyr 2.3% → 3.2%

    This is still conservative (3y history can't predict growth) but no
    longer systematically misreads recovery stocks. invest3 §8 "预期股息率"
    intent is preserved.
    """
    cutoff = date.today() - timedelta(days=years * 365)
    row = db.execute(
        select(func.avg(DividendRecord.amount_per_share))
        .where(
            DividendRecord.stock_code == code,
            DividendRecord.ex_date >= cutoff,
            DividendRecord.amount_per_share > 0,
        )
    ).scalar_one_or_none()
    return float(row) if row else None


def _paid_years_in_window(db: Session, code: str, years: int = 3) -> int:
    """F17 v2: count distinct years with at least one nonzero DPS in past N years.

    Used as dividend stability factor: forward_dyr = trailing_12m × (paid_years / N).
    A stock that paid dividends every year gets factor=1.0; a stock that
    skipped years gets penalized proportionally.
    """
    cutoff = date.today() - timedelta(days=years * 365)
    rows = db.execute(
        select(DividendRecord.ex_date)
        .where(
            DividendRecord.stock_code == code,
            DividendRecord.ex_date >= cutoff,
            DividendRecord.amount_per_share > 0,
        )
    ).scalars().all()
    return len({d.year for d in rows if d is not None})


def _latest_close_price(db: Session, code: str) -> float | None:
    """Return the latest close price for a stock, or None if no kline data."""
    from app.models.price_kline import PriceKline
    row = db.execute(
        select(PriceKline.close)
        .where(PriceKline.stock_code == code)
        .order_by(PriceKline.date.desc())
        .limit(1)
    ).scalar_one_or_none()
    return float(row) if row else None


def compute_forward_dyr_for_stock(
    db: Session, code: str, trailing_dyr: float | None = None
) -> float | None:
    """F17 v2 (2026-06-18): Forward DYR = trailing_12m_dyr × stability_factor.

    Algorithm (when Lixinger trailing_dyr is available):
        forward_dyr = trailing_dyr × (paid_years_in_3y / 3)

    Rationale:
    - Lixinger `dyr` is trailing 12-month dividend yield (based on actual
      past-year DPS / latest close). This is the most accurate "current
      paying power" data we have.
    - Multiplying by stability factor (= distinct paid years / N) discounts
      the trailing yield for stocks with interrupted dividend history. A
      stock that paid 3 of 3 years keeps full trailing; a stock that paid
      1 of 3 gets ×0.33 reflecting uncertainty about future payouts.
    - This is more accurate than the F17 v1 algorithm (3y avg DPS, nonzero
      only) which systematically underestimated banks by 3×.

    Fallback (when trailing_dyr is None or 0): use F17 v1 algorithm
    (3y avg nonzero DPS / latest close).

    Returns None when no dividend history AND no trailing_dyr — caller
    treats None as inconclusive (剔除).

    Real-world impact (spike 2026-06-18, assuming 3/3 paid years):
      002170 芭田股份: Lixinger dyr=6.6% → forward_dyr 6.6% (vs v1: 2.1%)
      601398 工商银行: Lixinger dyr=4.2% → forward_dyr 4.2% (vs v1: 2.7%)
      601166 兴业银行: Lixinger dyr=6.0% → forward_dyr 6.0% (vs v1: 4.8%)

    Note: forward_dyr is now a "trailing × stability" proxy, not a true
    forward projection. invest3 §8 "预期股息率" intent is preserved as
    long as the user reads it as "current paying power adjusted for
    stability". True forward projection (based on dividend guidance /
    earnings forecasts) needs data sources Lixinger doesn't provide.
    """
    # Try F17 v2 algorithm first
    if trailing_dyr is not None and trailing_dyr > 0:
        paid_years = _paid_years_in_window(db, code, years=3)
        if paid_years > 0:
            stability = min(paid_years / 3.0, 1.0)
            return trailing_dyr * stability

    # Fallback: F17 v1 algorithm (3y avg nonzero DPS / latest close)
    avg_per_share = _historical_avg_per_share(db, code)
    if avg_per_share is None or avg_per_share <= 0:
        return None
    price = _latest_close_price(db, code)
    if price is None or price <= 0:
        return None
    return avg_per_share / price


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
        elif dyr and dyr > 0:
            price = h.buy_price
            expected_per_share = dyr * price
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
