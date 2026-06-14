"""Test build_stock_context_at and its derived field helpers."""
from datetime import date, timedelta

import pytest

from app.models.historical_kline import HistoricalKline
from app.models.historical_valuation import HistoricalValuation
from app.models.stock import Stock
from app.services.point_in_time_context_service import (
    build_stock_context_at,
    _compute_percentile_at,
    _compute_price_drop_pct_at,
)


@pytest.fixture
def setup_with_window(db_session):
    """Seed 60 days of kline + valuation so percentile/drop helpers have data.

    pe_ttm oscillates 20-40 (not monotonic) so day 30 has pe=30, ~50% rank.
    pb oscillates 2-4 similarly. Kline highs grow so 52w_high comes from latest.
    """
    import math
    db_session.add(Stock(
        code="600519", name="贵州茅台", exchange="sh",
        industry="白酒", qiu_score=85,
    ))
    base_day = date(2024, 1, 1)
    for i in range(60):
        d = base_day + timedelta(days=i)
        # pe_ttm oscillates 20-40 via sine (period=60 days, so day 30 = peak=40, day 0/60 = trough=20)
        pe = 30.0 + 10.0 * math.sin(2 * math.pi * i / 60)
        pb = 3.0 + 1.0 * math.sin(2 * math.pi * i / 60)
        db_session.add(HistoricalValuation(
            stock_code="600519", date=d,
            pe_ttm=pe, pb=pb,
            dyr=0.025,
        ))
        # Kline: close=100 + small oscillation; high=close+5
        close = 100.0 + i + math.sin(i)
        db_session.add(HistoricalKline(
            stock_code="600519", date=d,
            open=close, high=close + 5, low=close - 5, close=close,
            volume=10000, amount=1000000,
        ))
    db_session.flush()
    return base_day


def test_build_stock_context_at_populates_basic_fields(db_session, setup_with_window):
    base_day = setup_with_window
    # Day 15: pe=30+10*sin(π/2)=40 (peak). Day 0: pe=20 (trough). Day 30: pe=20 (trough of next cycle).
    ctx = build_stock_context_at(db_session, "600519", base_day + timedelta(days=15))
    assert ctx.code == "600519"
    assert ctx.name == "贵州茅台"
    assert ctx.industry == "白酒"
    assert ctx.qiu_score == 85
    assert ctx.dyr is not None
    assert ctx.forward_dyr == ctx.dyr  # proxy
    assert ctx.price is not None


def test_compute_percentile_at_returns_correct_rank(db_session, setup_with_window):
    """60 days of oscillating pe_ttm (sin wave). Verify percentile varies with current.

    pe(i) = 30 + 10*sin(2π*i/60). Peak at i=15 (pe=40), trough at i=45 (pe=20).
    """
    base_day = setup_with_window
    # Day 15 = pe 40 (peak). With min_samples lowered, expect ~1.0 (everything <= 40)
    pct_peak = _compute_percentile_at(
        db_session, "600519",
        base_day + timedelta(days=15), "pe_ttm",
        years=1, min_samples=10,
    )
    assert pct_peak is not None
    assert pct_peak > 0.9  # peak is near max

    # Day 45 = pe 20 (trough). Window [0-45] has 46 records.
    # Values <= 20: only i=45 itself. So percentile = 1/46 ≈ 0.022
    pct_trough = _compute_percentile_at(
        db_session, "600519",
        base_day + timedelta(days=45), "pe_ttm", years=1,
    )
    assert pct_trough is not None
    assert pct_trough < 0.1  # trough is at very bottom
    assert pct_peak > pct_trough  # peak percentile > trough percentile


def test_compute_percentile_at_insufficient_samples(db_session, setup_with_window):
    """If window has < min_samples records, return None."""
    base_day = setup_with_window
    pct = _compute_percentile_at(
        db_session, "600519",
        base_day + timedelta(days=30), "pe_ttm",
        years=1, min_samples=100,  # demand more than we have
    )
    assert pct is None


def test_compute_percentile_at_missing_current_value(db_session, setup_with_window):
    """If current day has no valuation, return None."""
    base_day = setup_with_window
    pct = _compute_percentile_at(
        db_session, "600519",
        base_day + timedelta(days=90),  # outside seeded range
        "pe_ttm", years=1,
    )
    assert pct is None


def test_compute_price_drop_pct_at(db_session, setup_with_window):
    """Price drop = 1 - close/52w_high. Kline highs grow so latest is max."""
    base_day = setup_with_window
    # Day 30: high = close+5 = 130+5 = 135. Window 0-30 max high = 135 (day 30 itself).
    # drop = (135 - 130) / 135 ≈ 0.037
    drop = _compute_price_drop_pct_at(
        db_session, "600519", base_day + timedelta(days=30),
        window_days=60,
    )
    assert drop is not None
    assert 0 < drop < 0.1  # small drop, latest is near high


def test_compute_price_drop_pct_at_no_kline_at_day(db_session, setup_with_window):
    """If kline missing for the day, return None."""
    base_day = setup_with_window
    drop = _compute_price_drop_pct_at(
        db_session, "600519", base_day + timedelta(days=90),
    )
    assert drop is None


def test_build_stock_context_at_with_full_window(db_session, setup_with_window):
    """End-to-end: derived fields populate correctly given enough data."""
    base_day = setup_with_window
    # Day 45 = pe 20 (trough). Window has 46 records > min_samples=30.
    ctx = build_stock_context_at(db_session, "600519", base_day + timedelta(days=45))
    assert ctx.pe_pct_10y is not None
    assert 0 <= ctx.pe_pct_10y <= 1.0
    assert ctx.pb_pct_10y is not None
    assert ctx.price_drop_pct is not None
    assert 0 <= ctx.price_drop_pct < 0.2
