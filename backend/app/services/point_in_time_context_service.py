"""Point-in-time context builder for backtest engine.

Critical for backtest correctness: at day D, only financials whose
report_date <= D are "known". This avoids look-ahead bias.

get_publish_date handles the rare case where Lixinger returns a financial
record without reportDate — falls back to CSRC regulatory ceiling
(annual_report=120d, etc.) which is conservative (never leaks future data).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.historical_financial import HistoricalFinancial
from app.models.historical_kline import HistoricalKline
from app.models.historical_valuation import HistoricalValuation
from app.models.stock import Stock
from app.services.strategy_engine import StockContext


# CSRC 法定披露日上限(用 publish_date 缺失时兜底)
_CSRC_LIMITS_DAYS = {
    "annual_report": 120,
    "semi_annual_report": 60,
    "interim_report": 60,
    "first_quarterly_report": 30,
    "third_quarterly_report": 31,
}
_DEFAULT_FALLBACK_DAYS = 120


def get_publish_date(record: dict) -> Optional[date]:
    """Extract report_date from a Lixinger financial record.

    Falls back to period + CSRC max days by report_type if reportDate
    missing (conservative — never leaks future data).
    """
    # Try direct field
    rd_str = record.get("reportDate")
    if rd_str:
        pd = _parse_date(rd_str)
        if pd:
            return pd

    # Fallback: period + CSRC ceiling
    period_str = record.get("date") or record.get("period")
    if not period_str:
        return None
    period = _parse_date(period_str)
    if not period:
        return None
    report_type = record.get("reportType", "")
    days = _CSRC_LIMITS_DAYS.get(report_type, _DEFAULT_FALLBACK_DAYS)
    return period + timedelta(days=days)


def _parse_date(s) -> Optional[date]:
    if not s or not isinstance(s, str):
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


# --- Per-data-type queries ---

def get_kline_at(db: Session, stock_code: str, day: date) -> Optional[HistoricalKline]:
    """Get K-line for stock on specific day (or None)."""
    return db.execute(
        select(HistoricalKline).where(
            HistoricalKline.stock_code == stock_code,
            HistoricalKline.date == day,
        )
    ).scalar_one_or_none()


def get_valuation_at(db: Session, stock_code: str, day: date) -> Optional[HistoricalValuation]:
    """Get valuation for stock on specific day."""
    return db.execute(
        select(HistoricalValuation).where(
            HistoricalValuation.stock_code == stock_code,
            HistoricalValuation.date == day,
        )
    ).scalar_one_or_none()


def get_latest_financial_as_of(
    db: Session, stock_code: str, day: date
) -> Optional[HistoricalFinancial]:
    """Get most recent financial report PUBLISHED on or before `day`.

    Filters by report_date (NOT period) — point-in-time correctness.
    Returns None if no reports published by `day`.
    """
    return db.execute(
        select(HistoricalFinancial)
        .where(
            HistoricalFinancial.stock_code == stock_code,
            HistoricalFinancial.report_date <= day,
        )
        .order_by(desc(HistoricalFinancial.period))
        .limit(1)
    ).scalar_one_or_none()


# --- Composite context ---

@dataclass(frozen=True)
class PointInTimeContext:
    """Snapshot of all known data for a stock on a given day.

    Used by backtest engine to evaluate strategies.
    """
    stock_code: str
    day: date
    kline: Optional[HistoricalKline]
    valuation: Optional[HistoricalValuation]
    financial: Optional[HistoricalFinancial]
    """Most recent financial published by `day`."""


def build_context_at(
    db: Session, stock_code: str, day: date
) -> PointInTimeContext:
    """Assemble full point-in-time context for `stock_code` on `day`."""
    return PointInTimeContext(
        stock_code=stock_code,
        day=day,
        kline=get_kline_at(db, stock_code, day),
        valuation=get_valuation_at(db, stock_code, day),
        financial=get_latest_financial_as_of(db, stock_code, day),
    )


def build_stock_context_at(
    db: Session, stock_code: str, day: date
) -> StockContext:
    """Build a StockContext at a specific point in time.

    Wraps build_context_at + Stock table lookup to produce a StockContext
    consumable by strategy_engine.evaluate.

    Derived fields computed from historical windows:
    - pe_pct_10y / pb_pct_10y: percentile rank of current pe_ttm/pb within
      the [day-window_years, day] range. Window is best-effort — uses
      whatever historical_valuations data exists (may be < 10y if backfill
      was partial). Returns None if window has < 30 data points (statistically
      unstable).
    - price_drop_pct: 1 - close / 52w_high. Window uses historical_klines.
    - forward_dyr: proxy from trailing dyr (forward forecasts not stored).
      This is a documented approximation — trailing dyr = forward dyr when
      dividend is stable; differs when dividends change.
    - dividend_sustainability: PIT version of the production
      `dividend_sustainability_service.compute_sustainability_score` algorithm.
      Computes 3/4 factors (payout trend unavailable — `historical_financials`
      has no `dividend_payout_ratio` column). Max achievable score in PIT is
      80 instead of 100 — strategies with high thresholds (e.g. `>= 60`) are
      proportionally harder to satisfy.

    Not populated:
    - power_tier: from BusinessPattern, not loaded here.
    """
    pit = build_context_at(db, stock_code, day)
    stock = db.execute(
        select(Stock).where(Stock.code == stock_code)
    ).scalar_one_or_none()

    pe_pct_10y = _compute_percentile_at(
        db, stock_code, day, "pe_ttm", years=10,
    )
    pb_pct_10y = _compute_percentile_at(
        db, stock_code, day, "pb", years=10,
    )
    price_drop_pct = _compute_price_drop_pct_at(db, stock_code, day)
    dividend_sustainability = _compute_dividend_sustainability_at(
        db, stock_code, day
    )

    return StockContext(
        code=stock_code,
        name=stock.name if stock else "",
        industry=stock.industry if stock else None,
        security_theme=stock.security_theme if stock else None,
        tier=stock.tier if stock else None,
        qiu_score=stock.qiu_score if stock else None,
        hq_region=stock.hq_region if stock else None,
        has_mine=stock.has_mine if stock else None,
        domestic_leader=stock.domestic_leader if stock else None,
        expansion_outlook=stock.expansion_outlook if stock else None,
        geo_risk=stock.geo_risk if stock else None,

        # Valuation — dyr_fwd proxied from trailing dyr
        dyr=pit.valuation.dyr if pit.valuation else None,
        forward_dyr=pit.valuation.dyr if pit.valuation else None,
        pe_pct_10y=pe_pct_10y,
        pb_pct_10y=pb_pct_10y,

        # Financial
        ocf_to_ni=pit.financial.ocf_to_np_ratio if pit.financial else None,
        dividend_sustainability=dividend_sustainability,

        # Price + windowed price_drop_pct
        price=pit.kline.close if pit.kline else None,
        price_drop_pct=price_drop_pct,
    )


def _compute_dividend_sustainability_at(
    db: Session,
    stock_code: str,
    day: date,
) -> Optional[float]:
    """PIT version of dividend sustainability score (0-80 in PIT).

    Mirrors `dividend_sustainability_service.compute_sustainability_score`
    but queries only data PUBLISHED or OCCURRED on or before `day`.

    Factors computed (3/4):
    - OCF/NI ratio (max 40): HistoricalFinancial with report_date <= day
    - Dividend growth streak (max 30): DividendRecord with ex_date <= day
    - DYR vs historical median (max 10): HistoricalValuation with date <= day

    Skipped (1/4):
    - Payout ratio trend (max 20): HistoricalFinancial has no
      dividend_payout_ratio column. Returns 0 (not None) so total still sums.

    Returns None when both OCF/NI and dividend streak are unavailable
    (insufficient data to score).
    """
    ocf_ni_score = _score_ocf_ni_at(db, stock_code, day)
    growth_streak_score = _score_dividend_growth_streak_at(db, stock_code, day)
    payout_score = 0.0  # Skipped — HistoricalFinancial has no payout ratio
    dyr_score = _score_dyr_comparison_at(db, stock_code, day)

    if ocf_ni_score is None and growth_streak_score is None:
        return None

    total = (
        (ocf_ni_score or 0)
        + (growth_streak_score or 0)
        + payout_score
        + (dyr_score or 0)
    )
    return float(total)


def _score_ocf_ni_at(
    db: Session, stock_code: str, day: date
) -> Optional[float]:
    """Score OCF/NI ratio (max 40) using HistoricalFinancial published by `day`."""
    rows = db.execute(
        select(HistoricalFinancial)
        .where(
            HistoricalFinancial.stock_code == stock_code,
            HistoricalFinancial.report_date <= day,
        )
        .order_by(desc(HistoricalFinancial.period))
        .limit(4)
    ).scalars().all()

    if not rows:
        return None

    total_ocf = sum((r.operating_cash_flow or 0.0) for r in rows)
    total_ni = sum((r.net_profit or 0.0) for r in rows)

    if total_ni <= 0:
        return None

    ratio = total_ocf / total_ni
    if ratio >= 1.2:
        return 40.0
    elif ratio >= 1.0:
        return 30.0
    elif ratio >= 0.8:
        return 20.0
    elif ratio >= 0.5:
        return 10.0
    else:
        return 0.0


def _score_dividend_growth_streak_at(
    db: Session, stock_code: str, day: date
) -> Optional[float]:
    """Score dividend growth streak (max 30) using DividendRecord with ex_date <= day."""
    from app.models.dividend import DividendRecord

    try:
        window_start = date(day.year - 5, day.month, day.day)
    except ValueError:  # Feb 29 edge case
        window_start = date(day.year - 5, 3, 1)

    rows = db.execute(
        select(DividendRecord)
        .where(
            DividendRecord.stock_code == stock_code,
            DividendRecord.ex_date <= day,
            DividendRecord.ex_date >= window_start,
        )
        .order_by(desc(DividendRecord.ex_date))
    ).scalars().all()

    if not rows:
        return None

    yearly_totals: dict[int, float] = {}
    for r in rows:
        year = r.ex_date.year
        yearly_totals[year] = yearly_totals.get(year, 0.0) + r.amount_per_share

    if not yearly_totals:
        return None

    sorted_years = sorted(yearly_totals.keys(), reverse=True)

    streak = 0
    for i in range(len(sorted_years) - 1):
        current_year = sorted_years[i]
        next_year = sorted_years[i + 1]
        if yearly_totals[current_year] >= yearly_totals[next_year]:
            streak += 1
        else:
            break

    if streak >= 4:
        return 30.0
    elif streak == 3:
        return 24.0
    elif streak == 2:
        return 18.0
    elif streak == 1:
        return 12.0
    else:
        if len(sorted_years) >= 2:
            return 6.0
        else:
            return 0.0


def _score_dyr_comparison_at(
    db: Session, stock_code: str, day: date
) -> Optional[float]:
    """Score expected DYR vs historical 3y median (max 10)."""
    latest_val = db.execute(
        select(HistoricalValuation)
        .where(
            HistoricalValuation.stock_code == stock_code,
            HistoricalValuation.date <= day,
            HistoricalValuation.dyr.is_not(None),
        )
        .order_by(desc(HistoricalValuation.date))
        .limit(1)
    ).scalar_one_or_none()

    if latest_val is None or latest_val.dyr is None:
        return None

    expected_dyr = latest_val.dyr

    try:
        window_start = date(day.year - 3, day.month, day.day)
    except ValueError:
        window_start = date(day.year - 3, 3, 1)

    historical_dyrs = db.execute(
        select(HistoricalValuation.dyr)
        .where(
            HistoricalValuation.stock_code == stock_code,
            HistoricalValuation.date >= window_start,
            HistoricalValuation.date <= day,
            HistoricalValuation.dyr.is_not(None),
        )
    ).scalars().all()

    if not historical_dyrs:
        return None

    sorted_dyrs = sorted(historical_dyrs)
    median_dyr = sorted_dyrs[len(sorted_dyrs) // 2]
    if median_dyr == 0:
        return None

    ratio = expected_dyr / median_dyr
    if ratio >= 1.0:
        return 10.0
    elif ratio >= 0.8:
        return 5.0
    else:
        return 0.0


def _compute_percentile_at(
    db: Session,
    stock_code: str,
    day: date,
    field: str,
    years: int = 10,
    min_samples: int = 30,
) -> Optional[float]:
    """Percentile rank (0-1) of current field value within past window.

    Returns None when:
    - No valuation record exists at `day` (current value unknown)
    - Window has fewer than `min_samples` records (statistically unstable)
    - All historical values are None or non-numeric
    """
    current = db.execute(
        select(getattr(HistoricalValuation, field)).where(
            HistoricalValuation.stock_code == stock_code,
            HistoricalValuation.date == day,
        )
    ).scalar_one_or_none()
    if current is None:
        return None

    window_start = date(day.year - years, day.month, day.day)
    rows = db.execute(
        select(getattr(HistoricalValuation, field))
        .where(
            HistoricalValuation.stock_code == stock_code,
            HistoricalValuation.date >= window_start,
            HistoricalValuation.date <= day,
            getattr(HistoricalValuation, field).is_not(None),
        )
    ).scalars().all()
    if len(rows) < min_samples:
        return None

    # Percentile rank: fraction of historical values <= current
    le_count = sum(1 for v in rows if v is not None and v <= current)
    return le_count / len(rows)


def _compute_price_drop_pct_at(
    db: Session,
    stock_code: str,
    day: date,
    window_days: int = 366,
) -> Optional[float]:
    """Price drop from 52w high. Returns None if no kline data in window."""
    current_kline = db.execute(
        select(HistoricalKline.close).where(
            HistoricalKline.stock_code == stock_code,
            HistoricalKline.date == day,
        )
    ).scalar_one_or_none()
    if current_kline is None:
        return None

    from datetime import timedelta
    window_start = day - timedelta(days=window_days)
    high_52w = db.execute(
        select(HistoricalKline.high)
        .where(
            HistoricalKline.stock_code == stock_code,
            HistoricalKline.date >= window_start,
            HistoricalKline.date <= day,
        )
    ).scalars().all()
    if not high_52w:
        return None
    high = max(high_52w)
    if high <= 0:
        return None
    return (high - current_kline) / high
