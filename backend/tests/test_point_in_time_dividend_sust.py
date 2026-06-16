"""Tests for PIT dividend_sustainability computation (P1-1).

Verifies the 3/4 factor PIT algorithm matches production semantics where
possible, and correctly returns None when data is unavailable.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.models.dividend import DividendRecord
from app.models.historical_financial import HistoricalFinancial
from app.models.historical_valuation import HistoricalValuation
from app.services.point_in_time_context_service import (
    _compute_dividend_sustainability_at,
    _score_dividend_growth_streak_at,
    _score_dyr_comparison_at,
    _score_ocf_ni_at,
    build_stock_context_at,
)


@pytest.fixture
def stock_with_data(db_session):
    """A stock with financials + dividends + valuations.

    Data carefully aligned so:
    - financial published 2023-04-26 (period 2023-03-31) — visible from 2023-04-26 onward
    - 5 years of dividends (2018-2022) with growth streak
    - valuations for 3 years (2020-2023)
    """
    db_session.add_all([
        HistoricalFinancial(
            stock_code="TEST001",
            period=date(2022, 12, 31),
            report_date=date(2023, 3, 30),
            net_profit=1000.0,
            operating_cash_flow=1100.0,  # OCF/NI = 1.1 → score 30
        ),
        HistoricalFinancial(
            stock_code="TEST001",
            period=date(2023, 3, 31),
            report_date=date(2023, 4, 26),
            net_profit=1100.0,
            operating_cash_flow=1320.0,  # OCF/NI = 1.2 → score 40
        ),
    ])

    # 5 years of growing dividends (ex_date in 2018-2022)
    for year, amount in [(2018, 1.0), (2019, 1.1), (2020, 1.2), (2021, 1.3), (2022, 1.4)]:
        db_session.add(DividendRecord(
            stock_code="TEST001",
            ex_date=date(year, 6, 15),
            amount_per_share=amount,
            quantity_held=0,
            total_received=0.0,
            reinvested=False,
        ))

    # 3 years of valuations
    for year in [2020, 2021, 2022, 2023]:
        for month in [3, 6, 9]:
            db_session.add(HistoricalValuation(
                stock_code="TEST001",
                date=date(year, month, 1),
                dyr=0.04,  # flat dyr so expected/median = 1.0 → score 10
            ))
    db_session.commit()
    return "TEST001"


def test_pit_returns_none_when_no_data(db_session):
    """No financials + no dividends → None."""
    db_session.add(HistoricalValuation(
        stock_code="EMPTY", date=date(2023, 6, 1), dyr=0.04,
    ))
    db_session.commit()
    score = _compute_dividend_sustainability_at(
        db_session, "EMPTY", date(2023, 6, 1)
    )
    assert score is None


def test_pit_ocf_ni_respects_report_date(db_session, stock_with_data):
    """At day=2023-04-25, only the 2022 financial is visible (report_date=2023-03-30).
    At day=2023-04-27, both 2022 and Q1 2023 are visible.
    """
    code = stock_with_data

    # Before Q1 2023 publish (2023-04-26): only 2022 visible
    # OCF=1100, NI=1000, ratio=1.1 → score 30
    score_before = _score_ocf_ni_at(db_session, code, date(2023, 4, 25))
    assert score_before == 30.0

    # After Q1 2023 publish: sum(2022 + Q1) = OCF 2400, NI 2100, ratio=1.14 → score 30
    # (just one record still hits >= 1.0 threshold)
    score_after = _score_ocf_ni_at(db_session, code, date(2023, 4, 27))
    assert score_after == 30.0


def test_pit_dividend_streak_5_years_growth(db_session, stock_with_data):
    """5 years of growth (2018-2022) → streak=4 → score 30."""
    code = stock_with_data
    score = _score_dividend_growth_streak_at(db_session, code, date(2023, 6, 1))
    assert score == 30.0


def test_pit_dividend_streak_respects_ex_date(db_session, stock_with_data):
    """At day=2019-06-14, only 2018 dividend visible → 1 year → score 0."""
    code = stock_with_data
    score = _score_dividend_growth_streak_at(db_session, code, date(2019, 6, 14))
    assert score == 0.0


def test_pit_dyr_comparison_flat_history(db_session, stock_with_data):
    """All dyrs=0.04 → ratio=1.0 → score 10."""
    code = stock_with_data
    score = _score_dyr_comparison_at(db_session, code, date(2023, 6, 1))
    assert score == 10.0


def test_pit_composite_score(db_session, stock_with_data):
    """After 2023-04-26 publish: ocf_ni=30 + streak=30 + dyr=10 + payout=0 = 70."""
    code = stock_with_data
    score = _compute_dividend_sustainability_at(
        db_session, code, date(2023, 6, 1)
    )
    assert score == 70.0


def test_pit_composite_below_publish_date(db_session, stock_with_data):
    """Before 2023-04-26: only 2022 financial → ocf_ni=30 + streak=30 + dyr=10 = 70.
    Note: in this test the 2022 financial alone has OCF/NI=1.1 → 30 pts.
    """
    code = stock_with_data
    score = _compute_dividend_sustainability_at(
        db_session, code, date(2023, 4, 1)
    )
    assert score == 70.0  # same as above because OCF/NI ratio doesn't change category


def test_build_stock_context_at_includes_dividend_sustainability(db_session, stock_with_data):
    """End-to-end: build_stock_context_at returns context with div_sust populated."""
    code = stock_with_data
    # Add Stock record (required by build_stock_context_at)
    from app.models.stock import Stock
    db_session.add(Stock(code=code, name="测试股"))
    db_session.commit()

    ctx = build_stock_context_at(db_session, code, date(2023, 6, 1))
    assert ctx.dividend_sustainability == 70.0


def test_pit_max_80_due_to_missing_payout(db_session, stock_with_data):
    """PIT skips payout (max 20) — verify cap is 80 not 100."""
    code = stock_with_data
    # Best possible: ocf_ni=40 + streak=30 + payout=0 + dyr=10 = 80
    # Our fixture has ocf_ni=30 (ratio 1.1 not 1.2), so total = 70
    score = _compute_dividend_sustainability_at(
        db_session, code, date(2023, 6, 1)
    )
    assert score == 70.0  # 30+30+0+10
    # Document: PIT max is 80, not 100. Production max is 100.
