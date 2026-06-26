"""Tests for sell_trigger — signals 2 (valuation overvalued) and 3 (position overweight).

Covers:
- scan_valuation_overvalued: PE/PB percentile > 90% → TRIM 50% draft
- scan_position_overweight: weight > 15% → TRIM to 10% draft
- check_fundamental_deterioration: news_pulse/earnings_review → SELL 100% draft
- run_all_signals: aggregation
"""
from datetime import date, datetime

import pytest

from app.models.draft import Draft
from app.models.stock import Stock
from app.models.trade import Trade
from app.models.valuation import ValuationSnapshot
from app.services.sell_trigger import (
    scan_valuation_overvalued,
    scan_position_overweight,
    check_fundamental_deterioration,
    run_all_signals,
)


@pytest.fixture
def db_session():
    from tests.conftest import TestSessionLocal
    s = TestSessionLocal()
    try:
        yield s
    finally:
        s.close()


def _seed_position(db, code="600519", qty=100, price=100.0):
    db.add(Stock(code=code, name=code, prev_close=price))
    db.add(Trade(stock_code=code, side="BUY", price=price, quantity=qty,
                 filled_at=datetime(2026, 1, 10, 10, 0), total_value=price * qty,
                 source="manual"))
    db.commit()


def _seed_valuation(db, code="600519", pe_pct=95.0, pb_pct=80.0):
    db.add(ValuationSnapshot(
        stock_code=code,
        date=date(2026, 6, 26),
        pe_ttm=50.0,
        pb=5.0,
        pe_percentile_10y=pe_pct,
        pb_percentile_10y=pb_pct,
        dividend_yield=0.02,
    ))
    db.commit()


# ── Signal 2: Valuation overvalued ────────────────────────────────────────


def test_signal2_valuation_overvalued_pe_above_90(db_session):
    """PE percentile >= 90% should trigger TRIM 50% SELL draft."""
    _seed_position(db_session)
    _seed_valuation(db_session, pe_pct=95.0, pb_pct=80.0)

    triggers = scan_valuation_overvalued(db_session)
    db_session.commit()

    assert len(triggers) == 1
    assert triggers[0]["stock_code"] == "600519"

    draft = db_session.query(Draft).filter(Draft.code == "600519", Draft.side == "SELL").first()
    assert draft is not None
    assert draft.reduce_pct_of_position == 0.5  # TRIM 50%
    assert draft.step_kind == "thesis_breach"
    assert "触发 2" in draft.reason


def test_signal2_valuation_overvalued_pb_above_90(db_session):
    """PB percentile >= 90% should also trigger."""
    _seed_position(db_session)
    _seed_valuation(db_session, pe_pct=50.0, pb_pct=95.0)

    triggers = scan_valuation_overvalued(db_session)
    db_session.commit()

    assert len(triggers) == 1


def test_signal2_no_trigger_when_valuation_normal(db_session):
    """PE/PB both below 90% should not trigger."""
    _seed_position(db_session)
    _seed_valuation(db_session, pe_pct=60.0, pb_pct=50.0)

    triggers = scan_valuation_overvalued(db_session)
    assert len(triggers) == 0
    assert db_session.query(Draft).count() == 0


def test_signal2_no_trigger_when_no_valuation(db_session):
    """No valuation data should not trigger."""
    _seed_position(db_session)

    triggers = scan_valuation_overvalued(db_session)
    assert len(triggers) == 0


# ── Signal 3: Position overweight ─────────────────────────────────────────


def test_signal3_position_overweight_above_15(db_session):
    """Weight > 15% should trigger TRIM to 10%."""
    # Seed other stocks so the position isn't 100% weight
    _seed_position(db_session, code="600519", qty=200, price=100.0)
    _seed_valuation(db_session, pe_pct=60.0, pb_pct=50.0)  # normal valuation

    # Need at least 2 positions so weight < 100%
    db_session.add(Stock(code="000001", name="额", prev_close=10.0))
    db_session.add(Trade(stock_code="000001", side="BUY", price=10.0, quantity=1000,
                         filled_at=datetime(2026, 1, 10, 10, 0), total_value=10000.0,
                         source="manual"))
    db_session.commit()

    # Check 600519 weight: 200*100 = 20000 vs 000001: 1000*10 = 10000
    # Total = 30000, weight = 20000/30000 = 66.7% (well above 15%)
    triggers = scan_position_overweight(db_session)
    db_session.commit()

    assert len(triggers) == 1
    assert triggers[0]["stock_code"] == "600519"


def test_signal3_no_trigger_when_below_15(db_session):
    """Weight <= 15% should not trigger."""
    # Seed 8 equal-value positions so each is ~12.5% weight (< 15%)
    # Use TEST-prefix codes to avoid real price lookups
    codes = ["TEST001", "TEST002", "TEST003", "TEST004",
             "TEST005", "TEST006", "TEST007", "TEST008"]
    for code in codes:
        db_session.add(Stock(code=code, name=code, prev_close=10.0))
        db_session.add(Trade(stock_code=code, side="BUY", price=10.0, quantity=100,
                             filled_at=datetime(2026, 1, 10, 10, 0), total_value=1000.0,
                             source="manual"))
    db_session.commit()

    triggers = scan_position_overweight(db_session)
    assert len(triggers) == 0


# ── Signal 5: Fundamental deterioration ───────────────────────────────────


def test_signal5_news_pulse_thesis_review_triggers_sell(db_session):
    """news_pulse action=thesis_review → SELL 100%."""
    _seed_position(db_session)
    result = check_fundamental_deterioration(
        db_session,
        stock_code="600519",
        action_recommendation="thesis_review",
        pipeline_type="news_pulse",
        detail="ROE 持续下降, 收入增速跌破 10%",
    )
    db_session.commit()
    assert result is not None
    assert result["stock_code"] == "600519"

    draft = db_session.query(Draft).filter(Draft.code == "600519", Draft.side == "SELL").first()
    assert draft is not None
    assert draft.reduce_pct_of_position == 1.0  # SELL 100%


def test_signal5_earnings_review_invalidates_triggers_sell(db_session):
    """earnings_review thesis_impact=invalidates → SELL 100%."""
    _seed_position(db_session)
    result = check_fundamental_deterioration(
        db_session,
        stock_code="600519",
        action_recommendation="invalidates",
        pipeline_type="earnings_review",
        detail="营收造假嫌疑, 应收账款异常增长",
    )
    db_session.commit()
    assert result is not None

    draft = db_session.query(Draft).filter(Draft.code == "600519", Draft.side == "SELL").first()
    assert draft is not None


def test_signal5_news_pulse_observe_no_draft(db_session):
    """news_pulse action=observe → no sell draft."""
    _seed_position(db_session)
    result = check_fundamental_deterioration(
        db_session,
        stock_code="600519",
        action_recommendation="observe",
        pipeline_type="news_pulse",
        detail="临时市场波动",
    )
    assert result is None
    assert db_session.query(Draft).count() == 0


# ── run_all_signals ───────────────────────────────────────────────────────


def test_run_all_signals_aggregation(db_session):
    """run_all_signals should return summary with both signal results."""
    _seed_position(db_session, code="TEST001", qty=200, price=100.0)
    # Add enough other positions to keep TEST001 weight reasonable
    for c in ["TEST002", "TEST003", "TEST004", "TEST005"]:
        db_session.add(Stock(code=c, name=c, prev_close=10.0))
        db_session.add(Trade(stock_code=c, side="BUY", price=10.0, quantity=3000,
                             filled_at=datetime(2026, 1, 10, 10, 0), total_value=30000.0,
                             source="manual"))
    db_session.commit()

    result = run_all_signals(db_session)
    db_session.commit()

    assert isinstance(result, dict)
    assert "valuation_overvalued" in result
    assert "position_overweight" in result
    assert "total_drafts" in result
    assert result["total_drafts"] >= 0


def test_run_all_signals_empty(db_session):
    """No positions → no triggers."""
    result = run_all_signals(db_session)
    assert result["total_drafts"] == 0
    assert len(result["valuation_overvalued"]) == 0
    assert len(result["position_overweight"]) == 0
