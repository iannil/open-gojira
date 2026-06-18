"""Tests for dividend_projector_service — 股息收入预测."""

import pytest
from datetime import date

from tests.conftest import TestSessionLocal
from app.models.cashflow_goal import CashflowGoal
from app.models.dividend import DividendRecord
from app.models.holding import Holding
from app.models.price_kline import PriceKline
from app.models.stock import Stock
from app.models.valuation import ValuationSnapshot
from app.services.dividend_projector_service import compute_forward_dyr_for_stock, project


@pytest.fixture
def db():
    session = TestSessionLocal()
    yield session
    session.close()


class TestDividendProjectionEmpty:
    def test_no_holdings_returns_zero(self, db):
        result = project(db)
        assert result.next_12m_expected == 0.0
        assert result.by_holding == []
        assert result.trailing_12m_actual == 0.0


class TestDividendProjection:
    def test_projects_from_historical_dividends(self, db):
        db.add(Stock(code="601398", name="工商银行", industry="银行"))
        db.add(Holding(stock_code="601398", buy_date=date(2025, 1, 1),
                       buy_price=5.0, quantity=2000, stop_profit_price=999.0))
        db.add(DividendRecord(stock_code="601398", ex_date=date(2025, 6, 15),
                              amount_per_share=0.30, quantity_held=2000, total_received=600.0))
        db.add(DividendRecord(stock_code="601398", ex_date=date(2024, 6, 15),
                              amount_per_share=0.29, quantity_held=2000, total_received=580.0))
        db.add(ValuationSnapshot(stock_code="601398", date=date(2026, 6, 6),
                                 dividend_yield=0.06))
        db.commit()

        result = project(db)
        assert len(result.by_holding) == 1
        h = result.by_holding[0]
        assert h.code == "601398"
        assert h.expected_per_share > 0
        assert h.expected_total == h.expected_per_share * 2000
        assert h.expected_ex_month == 6

    def test_projects_from_yield_when_no_history(self, db):
        db.add(Stock(code="600028", name="中国石化", industry="石油"))
        db.add(Holding(stock_code="600028", buy_date=date(2025, 1, 1),
                       buy_price=6.0, quantity=1000, stop_profit_price=999.0))
        db.add(ValuationSnapshot(stock_code="600028", date=date(2026, 6, 6),
                                 dividend_yield=0.08))
        db.commit()

        result = project(db)
        assert len(result.by_holding) == 1
        h = result.by_holding[0]
        assert h.code == "600028"
        # Expected = dyr * buy_price * quantity = 0.08 * 6.0 * 1000 = 480
        assert h.expected_total > 0

    def test_with_cashflow_goal(self, db):
        db.add(Stock(code="601398", name="工商银行", industry="银行"))
        db.add(Holding(stock_code="601398", buy_date=date(2025, 1, 1),
                       buy_price=5.0, quantity=2000, stop_profit_price=999.0))
        db.add(DividendRecord(stock_code="601398", ex_date=date(2025, 6, 15),
                              amount_per_share=0.30, quantity_held=2000, total_received=600.0))
        db.add(ValuationSnapshot(stock_code="601398", date=date(2026, 6, 6),
                                 dividend_yield=0.06))
        db.add(CashflowGoal(
            id=1,
            annual_expense=50000,
            goal_multiple=20,
        ))
        db.commit()

        result = project(db)
        assert result.annual_passive_target == 1000000.0  # 50000 * 20
        assert result.dividend_gap is not None
        assert result.dividend_coverage is not None
        assert result.dividend_coverage < 1.0  # 600 < 100000


class TestTrailing12m:
    def test_trailing_12m_actual(self, db):
        db.add(DividendRecord(stock_code="X", ex_date=date(2026, 1, 15),
                              amount_per_share=0.10, quantity_held=100, total_received=10.0))
        db.add(DividendRecord(stock_code="X", ex_date=date(2025, 1, 15),
                              amount_per_share=0.10, quantity_held=100, total_received=10.0))
        db.commit()

        result = project(db)
        assert result.trailing_12m_actual == 10.0


class TestComputeForwardDyr:
    """G3: compute_forward_dyr_for_stock — 预期股息率 (forward DYR).

    Algorithm: 3-year avg dividend_per_share / latest_close_price.
    Returns None when dividend history missing OR price missing.
    """

    def test_returns_none_when_no_dividend_history(self, db):
        db.add(Stock(code="999001", name="无分红新股"))
        db.add(PriceKline(stock_code="999001", date=date(2026, 6, 13),
                          open=10.0, high=10.5, low=9.8, close=10.0, volume=1000))
        db.commit()

        result = compute_forward_dyr_for_stock(db, "999001")
        assert result is None

    def test_returns_none_when_no_price(self, db):
        db.add(Stock(code="999002", name="停牌股"))
        db.add(DividendRecord(stock_code="999002", ex_date=date(2025, 6, 15),
                              amount_per_share=0.50, quantity_held=0, total_received=0.0))
        db.add(DividendRecord(stock_code="999002", ex_date=date(2024, 6, 15),
                              amount_per_share=0.48, quantity_held=0, total_received=0.0))
        db.commit()

        result = compute_forward_dyr_for_stock(db, "999002")
        assert result is None

    def test_returns_float_when_history_and_price_present(self, db):
        db.add(Stock(code="999003", name="稳定分红股"))
        # 3-year history: 0.30, 0.32, 0.34 → avg 0.32
        db.add(DividendRecord(stock_code="999003", ex_date=date(2026, 6, 15),
                              amount_per_share=0.34, quantity_held=0, total_received=0.0))
        db.add(DividendRecord(stock_code="999003", ex_date=date(2025, 6, 15),
                              amount_per_share=0.32, quantity_held=0, total_received=0.0))
        db.add(DividendRecord(stock_code="999003", ex_date=date(2024, 6, 15),
                              amount_per_share=0.30, quantity_held=0, total_received=0.0))
        # Latest close 8.0
        db.add(PriceKline(stock_code="999003", date=date(2026, 6, 13),
                          open=8.0, high=8.2, low=7.9, close=8.0, volume=1000))
        db.commit()

        result = compute_forward_dyr_for_stock(db, "999003")
        assert result is not None
        # avg_per_share=0.32, price=8.0 → 0.04
        assert abs(result - 0.04) < 1e-6

    def test_uses_latest_close_when_multiple_klines(self, db):
        db.add(Stock(code="999004", name="多K线股"))
        db.add(DividendRecord(stock_code="999004", ex_date=date(2025, 6, 15),
                              amount_per_share=0.40, quantity_held=0, total_received=0.0))
        # Multiple klines — latest by date should be picked
        db.add(PriceKline(stock_code="999004", date=date(2026, 6, 10),
                          open=8.0, high=8.2, low=7.9, close=8.0, volume=1000))
        db.add(PriceKline(stock_code="999004", date=date(2026, 6, 13),
                          open=10.0, high=10.5, low=9.8, close=10.0, volume=2000))
        db.commit()

        result = compute_forward_dyr_for_stock(db, "999004")
        # avg=0.40, latest close=10.0 → 0.04
        assert result is not None
        assert abs(result - 0.04) < 1e-6

    def test_ignores_dividends_older_than_3_years(self, db):
        """Old dividends should not skew the average."""
        db.add(Stock(code="999005", name="分红变化股"))
        # 5-year-old dividend (should be excluded)
        db.add(DividendRecord(stock_code="999005", ex_date=date(2021, 6, 15),
                              amount_per_share=10.0, quantity_held=0, total_received=0.0))
        # Recent 3-year dividends
        db.add(DividendRecord(stock_code="999005", ex_date=date(2026, 6, 15),
                              amount_per_share=0.30, quantity_held=0, total_received=0.0))
        db.add(PriceKline(stock_code="999005", date=date(2026, 6, 13),
                          open=10.0, high=10.5, low=9.8, close=10.0, volume=1000))
        db.commit()

        result = compute_forward_dyr_for_stock(db, "999005")
        # 3-year window only has 0.30 → avg 0.30; price 10 → 0.03
        assert result is not None
        assert abs(result - 0.03) < 1e-6


# ── F17 (2026-06-18): forward_dyr should exclude DPS=0 years ─────────────


def test_historical_avg_per_share_excludes_zero_dps(db_session):
    """F17: years with DPS=0 should NOT pull down the average."""
    from datetime import date, timedelta
    from app.models.dividend import DividendRecord
    from app.services.dividend_projector_service import _historical_avg_per_share

    today = date.today()
    db_session.add_all([
        # 3 years of data, but 2 years had DPS=0 (经营困难期)
        DividendRecord(stock_code="TEST001", ex_date=today - timedelta(days=30),
                       amount_per_share=0.50, quantity_held=100, total_received=0.0),
        DividendRecord(stock_code="TEST001", ex_date=today - timedelta(days=400),
                       amount_per_share=0.00, quantity_held=100, total_received=0.0),
        DividendRecord(stock_code="TEST001", ex_date=today - timedelta(days=750),
                       amount_per_share=0.00, quantity_held=100, total_received=0.0),
    ])
    db_session.flush()

    avg = _historical_avg_per_share(db_session, "TEST001", years=3)
    # Old algorithm: (0.5+0+0)/3 = 0.167
    # New algorithm: (0.5)/1 = 0.5
    assert avg == 0.5, f"Expected 0.5 (only counting paid years), got {avg}"


def test_historical_avg_per_share_returns_none_when_all_zero(db_session):
    """F17: if no year paid dividends, return None (inconclusive)."""
    from datetime import date, timedelta
    from app.models.dividend import DividendRecord
    from app.services.dividend_projector_service import _historical_avg_per_share

    today = date.today()
    db_session.add_all([
        DividendRecord(stock_code="TEST002", ex_date=today - timedelta(days=30),
                       amount_per_share=0.00, quantity_held=100, total_received=0.0),
        DividendRecord(stock_code="TEST002", ex_date=today - timedelta(days=400),
                       amount_per_share=0.00, quantity_held=100, total_received=0.0),
    ])
    db_session.flush()

    avg = _historical_avg_per_share(db_session, "TEST002", years=3)
    assert avg is None, f"Expected None when no paid years, got {avg}"


def test_compute_forward_dyr_recovery_stock_not_underestimated(db_session):
    """F17 integration:芭田-like recovery stock should get realistic forward_dyr."""
    from datetime import date, timedelta
    from app.models.dividend import DividendRecord
    from app.models.price_kline import PriceKline
    from app.services.dividend_projector_service import compute_forward_dyr_for_stock

    today = date.today()
    # Recovery stock: 2023-2024 paid 0, 2025 paid 0.30, 2026 paid 0.50
    db_session.add_all([
        DividendRecord(stock_code="TEST003", ex_date=today - timedelta(days=30),
                       amount_per_share=0.50, quantity_held=100, total_received=0.0),
        DividendRecord(stock_code="TEST003", ex_date=today - timedelta(days=400),
                       amount_per_share=0.30, quantity_held=100, total_received=0.0),
        DividendRecord(stock_code="TEST003", ex_date=today - timedelta(days=750),
                       amount_per_share=0.00, quantity_held=100, total_received=0.0),
        PriceKline(stock_code="TEST003", date=today, open=10, high=10.5,
                   low=9.8, close=10.0, volume=1000),
    ])
    db_session.flush()

    fd = compute_forward_dyr_for_stock(db_session, "TEST003")
    # Old: (0.5+0.3+0)/3 / 10 = 0.0267 (2.67%)
    # New: (0.5+0.3)/2 / 10 = 0.040 (4.0%)
    assert fd is not None
    assert 0.039 <= fd <= 0.041, f"Expected ~4.0% forward_dyr, got {fd}"


# ── F17 v2 (2026-06-18): forward_dyr = trailing_dyr × stability ──────────


def test_compute_forward_dyr_v2_uses_trailing_dyr_with_stability(db_session):
    """F17 v2: trailing_dyr × (paid_years_3y / 3)."""
    from datetime import date, timedelta
    from app.models.dividend import DividendRecord
    from app.services.dividend_projector_service import compute_forward_dyr_for_stock

    today = date.today()
    # Stock paid dividends every year for 3 years → stability=1.0
    db_session.add_all([
        DividendRecord(stock_code="TEST_V2_1", ex_date=today - timedelta(days=30),
                       amount_per_share=0.50, quantity_held=100, total_received=0.0),
        DividendRecord(stock_code="TEST_V2_1", ex_date=today - timedelta(days=400),
                       amount_per_share=0.30, quantity_held=100, total_received=0.0),
        DividendRecord(stock_code="TEST_V2_1", ex_date=today - timedelta(days=750),
                       amount_per_share=0.20, quantity_held=100, total_received=0.0),
    ])
    db_session.flush()

    # trailing_dyr=0.06 (6%), 3/3 paid years → forward_dyr=0.06
    fd = compute_forward_dyr_for_stock(db_session, "TEST_V2_1", trailing_dyr=0.06)
    assert fd is not None
    assert abs(fd - 0.06) < 1e-6, f"Expected 0.06, got {fd}"


def test_compute_forward_dyr_v2_discounts_for_interrupted_history(db_session):
    """F17 v2: stock with only 1 paid year out of 3 → ×1/3 factor."""
    from datetime import date, timedelta
    from app.models.dividend import DividendRecord
    from app.services.dividend_projector_service import compute_forward_dyr_for_stock

    today = date.today()
    # Only 1 paid year (2026), 2 skipped (2025/2024)
    db_session.add_all([
        DividendRecord(stock_code="TEST_V2_2", ex_date=today - timedelta(days=30),
                       amount_per_share=0.50, quantity_held=100, total_received=0.0),
    ])
    db_session.flush()

    # trailing_dyr=0.06, 1/3 paid years → forward_dyr=0.02
    fd = compute_forward_dyr_for_stock(db_session, "TEST_V2_2", trailing_dyr=0.06)
    assert fd is not None
    assert abs(fd - 0.02) < 1e-6, f"Expected 0.02 (0.06 × 1/3), got {fd}"


def test_compute_forward_dyr_v2_falls_back_when_no_trailing(db_session):
    """F17 v2: when trailing_dyr is None, fallback to F17 v1 algorithm."""
    from datetime import date, timedelta
    from app.models.dividend import DividendRecord
    from app.models.price_kline import PriceKline
    from app.services.dividend_projector_service import compute_forward_dyr_for_stock

    today = date.today()
    db_session.add_all([
        DividendRecord(stock_code="TEST_V2_3", ex_date=today - timedelta(days=30),
                       amount_per_share=0.50, quantity_held=100, total_received=0.0),
        DividendRecord(stock_code="TEST_V2_3", ex_date=today - timedelta(days=400),
                       amount_per_share=0.30, quantity_held=100, total_received=0.0),
        PriceKline(stock_code="TEST_V2_3", date=today, open=10, high=10.5,
                   low=9.8, close=10.0, volume=1000),
    ])
    db_session.flush()

    # No trailing_dyr → fallback: (0.5+0.3)/2 / 10 = 0.04
    fd = compute_forward_dyr_for_stock(db_session, "TEST_V2_3", trailing_dyr=None)
    assert fd is not None
    assert abs(fd - 0.04) < 1e-6, f"Expected 0.04 (fallback v1 algorithm), got {fd}"


def test_compute_forward_dyr_v2_returns_none_when_no_history_at_all(db_session):
    """F17 v2: no trailing_dyr AND no paid years → None."""
    from app.services.dividend_projector_service import compute_forward_dyr_for_stock

    fd = compute_forward_dyr_for_stock(db_session, "NONEXISTENT_CODE", trailing_dyr=None)
    assert fd is None


def test_compute_forward_dyr_v2_returns_none_when_zero_trailing(db_session):
    """F17 v2: trailing_dyr=0 should not produce forward_dyr (fall back)."""
    from datetime import date, timedelta
    from app.models.dividend import DividendRecord
    from app.services.dividend_projector_service import compute_forward_dyr_for_stock

    today = date.today()
    # No dividend history → fallback returns None
    fd = compute_forward_dyr_for_stock(db_session, "TEST_V2_4", trailing_dyr=0.0)
    assert fd is None, f"Expected None when trailing_dyr=0 and no history, got {fd}"
