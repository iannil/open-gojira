"""Tests for portfolio_risk_service — invest2 §7 平方差魔咒实时指标."""
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.historical_kline import HistoricalKline
from app.models.stock import Stock
from app.models.trade import Trade
from app.services.portfolio_risk_service import (
    PortfolioRisk,
    compute_portfolio_risk,
    _annual_volatility,
    _daily_returns,
    _max_drawdown_in_window,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _add_stock(db, code="600519", name="贵州茅台", industry="白酒"):
    s = Stock(code=code, name=name, industry=industry)
    db.add(s)
    db.commit()
    return s


def _add_buy_trade(db, code, qty=100, price=100.0, days_ago=5):
    t = Trade(
        stock_code=code,
        side="BUY",
        price=price,
        quantity=qty,
        filled_at=datetime.now() - timedelta(days=days_ago),
        total_value=qty * price,
        source="manual",
    )
    db.add(t)
    db.commit()
    return t


def _add_klines(db, code, prices: list[float], start_days_ago: int = 95):
    """Add daily klines with given close prices, ending today."""
    today = date.today()
    start = today - timedelta(days=start_days_ago)
    for i, p in enumerate(prices):
        db.add(HistoricalKline(
            stock_code=code,
            date=start + timedelta(days=i),
            open=p, high=p, low=p, close=p, volume=1000,
        ))
    db.commit()


# ---------------------------------------------------------------------------
# Empty / no-holdings cases
# ---------------------------------------------------------------------------


class TestNoHoldings:
    def test_no_holdings_returns_none_metrics(self, db_session):
        result = compute_portfolio_risk(db_session)
        assert result.has_holdings is False
        assert result.holdings_count == 0
        assert result.annual_volatility is None
        assert result.max_drawdown_30d is None
        assert result.max_drawdown_90d is None
        assert result.sharpe_proxy is None


# ---------------------------------------------------------------------------
# Single holding
# ---------------------------------------------------------------------------


class TestSingleHolding:
    def test_with_klines_computes_metrics(self, db_session):
        _add_stock(db_session, "600519")
        _add_buy_trade(db_session, "600519", qty=100, price=100)
        # 30 days of slight up/down movement
        prices = [100 + i * 0.5 + ((-1) ** i) for i in range(30)]
        _add_klines(db_session, "600519", prices, start_days_ago=35)

        result = compute_portfolio_risk(db_session)
        assert result.has_holdings is True
        assert result.holdings_count == 1
        assert result.window_days > 0
        assert result.annual_volatility is not None
        assert result.annual_volatility > 0
        assert result.max_drawdown_30d is not None
        assert result.max_drawdown_30d <= 0  # negative or zero
        assert result.sharpe_proxy is not None

    def test_no_klines_returns_none_metrics_with_warning(self, db_session):
        _add_stock(db_session, "600519")
        _add_buy_trade(db_session, "600519", qty=100, price=100)
        # No klines added

        result = compute_portfolio_risk(db_session)
        assert result.has_holdings is True
        assert result.holdings_count == 1
        assert result.window_days == 0
        assert result.annual_volatility is None
        assert any("600519" in e for e in result.errors)

    def test_single_kline_no_returns(self, db_session):
        """Only one kline row → no daily returns computable."""
        _add_stock(db_session, "600519")
        _add_buy_trade(db_session, "600519", qty=100, price=100)
        _add_klines(db_session, "600519", [100], start_days_ago=1)

        result = compute_portfolio_risk(db_session)
        assert result.has_holdings is True
        assert result.window_days >= 1  # at least the one row
        assert result.annual_volatility is None  # < 2 returns


# ---------------------------------------------------------------------------
# Pure helper tests
# ---------------------------------------------------------------------------


class TestAnnualVolatility:
    def test_zero_volatility_for_constant_series(self):
        vol = _annual_volatility([0.0, 0.0, 0.0, 0.0])
        assert vol == 0.0

    def test_none_for_short_series(self):
        assert _annual_volatility([0.05]) is None
        assert _annual_volatility([]) is None

    def test_positive_for_moving_series(self):
        vol = _annual_volatility([0.01, -0.01, 0.02, -0.02, 0.01])
        assert vol > 0


class TestDailyReturns:
    def test_empty_for_short_series(self):
        assert _daily_returns([]) == []
        assert _daily_returns([(date.today(), 100.0)]) == []

    def test_correct_arithmetic(self):
        series = [
            (date(2026, 1, 1), 100.0),
            (date(2026, 1, 2), 110.0),  # +10%
            (date(2026, 1, 3), 99.0),   # -10%
        ]
        returns = _daily_returns(series)
        assert len(returns) == 2
        assert returns[0] == pytest.approx(0.10, abs=1e-6)
        assert returns[1] == pytest.approx(-0.10, abs=1e-6)


class TestMaxDrawdownInWindow:
    def test_none_for_empty(self):
        assert _max_drawdown_in_window([], 30) is None

    def test_correct_drawdown(self):
        """Peak 100 → trough 80 = -20% drawdown."""
        today = date.today()
        series = [
            (today - timedelta(days=20), 100.0),
            (today - timedelta(days=15), 80.0),
            (today - timedelta(days=10), 90.0),
        ]
        mdd = _max_drawdown_in_window(series, 30)
        assert mdd == pytest.approx(-0.20, abs=1e-6)

    def test_window_filter(self):
        """Older peak outside window should not count."""
        today = date.today()
        series = [
            (today - timedelta(days=60), 100.0),  # outside 30d window
            (today - timedelta(days=29), 95.0),   # peak within window
            (today - timedelta(days=20), 90.0),   # trough
        ]
        mdd = _max_drawdown_in_window(series, 30)
        # Within window: peak 95, trough 90 → -5.26%
        assert mdd is not None
        assert mdd == pytest.approx(-5 / 95, abs=1e-4)
