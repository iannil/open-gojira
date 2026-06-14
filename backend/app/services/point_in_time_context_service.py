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

    Fields requiring windowed computation (pe_pct_10y, pb_pct_10y,
    price_52w_high, price_drop_pct, dividend_sustainability) are left None.
    The backtest engine or spot-check script can populate these via separate
    queries when needed; for slice verification the basic fields suffice.

    Forward dyr is left None — historical forward dividend forecasts are
    not stored; only realized dyr from HistoricalValuation is available.
    """
    pit = build_context_at(db, stock_code, day)
    stock = db.execute(
        select(Stock).where(Stock.code == stock_code)
    ).scalar_one_or_none()

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

        # Valuation
        dyr=pit.valuation.dyr if pit.valuation else None,
        # pe_pct_10y / pb_pct_10y need windowed computation — None here

        # Financial
        ocf_to_ni=pit.financial.ocf_to_np_ratio if pit.financial else None,
        # dividend_sustainability needs dividend history — None here

        # Price
        price=pit.kline.close if pit.kline else None,
        # price_52w_high / price_drop_pct need windowed computation — None here

        # power_tier from business pattern — not loaded here, caller adds if needed
    )
