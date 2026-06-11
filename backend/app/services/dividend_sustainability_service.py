"""Dividend sustainability scoring service.

Computes a composite 0-100 score based on:
- OCF/NI ratio (cash backing of profits): 40 points
- Dividend growth streak (consecutive years of non-decreasing dividends): 30 points
- Payout ratio trend (sustainable payout level): 20 points
- Expected DYR vs historical DYR comparison: 10 points
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.dividend import DividendRecord
from app.models.financial import FinancialStatement
from app.models.valuation import ValuationSnapshot


def compute_sustainability_score(db: Session, code: str) -> Optional[float]:
    """Compute dividend sustainability score (0-100) for a stock.

    Returns None if insufficient data.
    """
    # Factor 1: OCF/NI ratio (40 pts)
    ocf_ni_score = _score_ocf_ni(db, code)

    # Factor 2: Dividend growth streak (30 pts)
    growth_streak_score = _score_dividend_growth_streak(db, code)

    # Factor 3: Payout ratio trend (20 pts)
    payout_score = _score_payout_trend(db, code)

    # Factor 4: Expected vs historical DYR (10 pts)
    dyr_score = _score_dyr_comparison(db, code)

    if ocf_ni_score is None and growth_streak_score is None:
        return None  # Insufficient data

    total = (ocf_ni_score or 0) + (growth_streak_score or 0) + (payout_score or 0) + (dyr_score or 0)
    return float(total)


def _score_ocf_ni(db: Session, code: str) -> Optional[float]:
    """Score OCF/NI ratio (40 points max).

    Uses last 4 reports (1 year of quarterly data).
    Scoring:
    - ocf/ni >= 1.2 → 40
    - ocf/ni >= 1.0 → 30
    - ocf/ni >= 0.8 → 20
    - ocf/ni >= 0.5 → 10
    - else → 0
    """
    rows = db.execute(
        select(FinancialStatement)
        .where(FinancialStatement.stock_code == code)
        .order_by(desc(FinancialStatement.report_date))
        .limit(4)
    ).scalars().all()

    if not rows:
        return None

    total_ocf = sum((r.operating_cash_flow or 0.0) for r in rows)
    total_ni = sum((r.net_profit or 0.0) for r in rows)

    if total_ni <= 0:
        return None  # No profit or negative profit

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


def _score_dividend_growth_streak(db: Session, code: str) -> Optional[float]:
    """Score dividend growth streak (30 points max).

    Checks last 5 years of dividends for consecutive non-decreasing payments.
    Scoring:
    - 5+ years → 30
    - 4 years → 24
    - 3 years → 18
    - 2 years → 12
    - 1 year → 6
    - 0 years → 0
    """
    # Get dividends from last 5 years
    five_years_ago = date.today().replace(year=date.today().year - 5)
    rows = db.execute(
        select(DividendRecord)
        .where(
            DividendRecord.stock_code == code,
            DividendRecord.ex_date >= five_years_ago
        )
        .order_by(desc(DividendRecord.ex_date))
    ).scalars().all()

    if not rows:
        return None

    # Group by year and sum dividends per year
    yearly_totals: dict[int, float] = {}
    for r in rows:
        year = r.ex_date.year
        yearly_totals[year] = yearly_totals.get(year, 0.0) + r.amount_per_share

    if not yearly_totals:
        return None

    # Sort years descending (most recent first)
    sorted_years = sorted(yearly_totals.keys(), reverse=True)

    # Count consecutive years with non-decreasing dividends
    # We count how many consecutive year-over-year comparisons show no decrease
    streak = 0
    for i in range(len(sorted_years) - 1):
        current_year = sorted_years[i]
        next_year = sorted_years[i + 1]
        if yearly_totals[current_year] >= yearly_totals[next_year]:
            streak += 1
        else:
            break

    # The streak count is the number of successful comparisons
    # 4 comparisons = 5 years of growth
    # Score based on streak (number of consecutive non-decreasing transitions)
    if streak >= 4:
        return 30.0  # 5+ years of growth
    elif streak == 3:
        return 24.0  # 4 years of growth
    elif streak == 2:
        return 18.0  # 3 years of growth
    elif streak == 1:
        return 12.0  # 2 years of growth
    else:
        # streak == 0 means either only 1 year of data or first comparison failed
        # If we have at least 2 years but streak is 0, that means the most recent
        # year was less than the previous year - a dividend cut
        if len(sorted_years) >= 2:
            return 6.0  # 1 year (only the most recent)
        else:
            return 0.0  # No meaningful streak


def _score_payout_trend(db: Session, code: str) -> Optional[float]:
    """Score payout ratio trend (20 points max).

    Checks if payout ratio is stable or decreasing (healthy).
    Scoring:
    - stable/decreasing → 20
    - slight increase (< 10% rise) → 10
    - rapid increase (>= 10% rise) → 0
    """
    rows = db.execute(
        select(FinancialStatement)
        .where(
            FinancialStatement.stock_code == code,
            FinancialStatement.dividend_payout_ratio.is_not(None)
        )
        .order_by(desc(FinancialStatement.report_date))
        .limit(8)  # 2 years of quarterly data
    ).scalars().all()

    if len(rows) < 2:
        return None

    # Compare latest 4 quarters (1 year) with previous 4 quarters
    recent = rows[:4]
    older = rows[4:8]

    if not recent or not older:
        return None

    avg_recent = sum((r.dividend_payout_ratio or 0.0) for r in recent) / len(recent)
    avg_older = sum((r.dividend_payout_ratio or 0.0) for r in older) / len(older)

    if avg_older == 0:
        return None

    change_pct = (avg_recent - avg_older) / avg_older

    if change_pct <= 0:
        return 20.0  # Stable or decreasing
    elif change_pct < 0.1:  # Less than 10% increase
        return 10.0
    else:
        return 0.0  # Rapid increase


def _score_dyr_comparison(db: Session, code: str) -> Optional[float]:
    """Score expected DYR vs historical DYR (10 points max).

    If expected DYR >= historical median, stock is getting cheaper (good).
    Scoring:
    - expected >= median → 10
    - expected within 80% of median → 5
    - else → 0
    """
    # Get latest valuation for expected DYR
    latest_val = db.execute(
        select(ValuationSnapshot)
        .where(ValuationSnapshot.stock_code == code)
        .order_by(desc(ValuationSnapshot.date))
        .limit(1)
    ).scalar_one_or_none()

    if latest_val is None or latest_val.dividend_yield is None:
        return None

    expected_dyr = latest_val.dividend_yield

    # Get historical DYR values (last 3 years)
    three_years_ago = date.today().replace(year=date.today().year - 3)
    historical_rows = db.execute(
        select(ValuationSnapshot)
        .where(
            ValuationSnapshot.stock_code == code,
            ValuationSnapshot.date >= three_years_ago,
            ValuationSnapshot.dividend_yield.is_not(None)
        )
        .order_by(ValuationSnapshot.date)
    ).scalars().all()

    if not historical_rows:
        return None

    # Calculate median historical DYR
    dyrs = sorted([r.dividend_yield for r in historical_rows])
    median_dyr = dyrs[len(dyrs) // 2]

    if median_dyr == 0:
        return None

    ratio = expected_dyr / median_dyr

    if ratio >= 1.0:
        return 10.0
    elif ratio >= 0.8:
        return 5.0
    else:
        return 0.0
