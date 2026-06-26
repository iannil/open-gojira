"""Tests for holding_service — portfolio analytics derived from the Trade ledger.

Q2-A (2026-06-26): positions/P&L come from trades via position_service; there is
no Holding write path. These tests seed BUY/SELL trades and exercise the
surviving analytics (list / summary / rebalancing). Retired and therefore not
tested here: create/update/delete/sell_holding and per-holding stop-profit.
"""

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from unittest.mock import patch

from app.db.base import Base
from app.models.stock import Stock
from app.models.trade import Trade
from app.services import holding_service


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def sample_stock(db_session: Session) -> Stock:
    stock = Stock(code="600519", name="Kweichow Moutai", industry="Beverage")
    db_session.add(stock)
    db_session.commit()
    return stock


@pytest.fixture
def second_stock(db_session: Session) -> Stock:
    stock = Stock(code="000858", name="Wuliangye", industry="Beverage")
    db_session.add(stock)
    db_session.commit()
    return stock


@pytest.fixture
def bank_stock(db_session: Session) -> Stock:
    stock = Stock(code="601398", name="ICBC", industry="Banking")
    db_session.add(stock)
    db_session.commit()
    return stock


def _buy(db, code="600519", quantity=100, price=100.0, when=None):
    """Seed a BUY trade. total_value = price*quantity (no fees) → avg_cost == price."""
    when = when or datetime(2025, 1, 10, 10, 0)
    db.add(Trade(stock_code=code, side="BUY", price=price, quantity=quantity,
                 filled_at=when, total_value=price * quantity, source="manual"))
    db.commit()


def _sell(db, code="600519", quantity=100, price=110.0, when=None):
    when = when or datetime(2025, 6, 1, 10, 0)
    db.add(Trade(stock_code=code, side="SELL", price=price, quantity=-quantity,
                 filled_at=when, total_value=price * quantity, source="manual"))
    db.commit()


# ===========================================================================
# list_holdings (derived open positions)
# ===========================================================================


class TestListHoldings:
    def test_empty_portfolio(self, db_session: Session):
        assert holding_service.list_holdings(db_session) == []

    def test_list_all_positions(self, db_session: Session, sample_stock, bank_stock):
        _buy(db_session, code="600519")
        _buy(db_session, code="601398", price=5.0, quantity=1000)
        with patch("app.services.holding_service._get_cached_price", return_value=None):
            holdings = holding_service.list_holdings(db_session)
        assert {h["stock_code"] for h in holdings} == {"600519", "601398"}

    def test_fully_sold_position_excluded(self, db_session: Session, sample_stock, bank_stock):
        _buy(db_session, code="600519")
        _buy(db_session, code="601398", price=5.0, quantity=1000)
        _sell(db_session, code="600519", quantity=100)  # fully close 600519
        with patch("app.services.holding_service._get_cached_price", return_value=None):
            holdings = holding_service.list_holdings(db_session)
        assert [h["stock_code"] for h in holdings] == ["601398"]


# ===========================================================================
# get_portfolio_summary
# ===========================================================================


class TestGetPortfolioSummary:
    def test_empty_portfolio(self, db_session: Session):
        summary = holding_service.get_portfolio_summary(db_session)
        assert summary["total_cost"] == 0
        assert summary["total_value"] == 0
        assert summary["total_pnl"] is None
        assert summary["total_pnl_pct"] is None
        assert summary["position_count"] == 0
        assert summary["holdings"] == []
        assert summary["warnings"] == []

    def test_total_pnl_none_when_no_prices(self, db_session: Session, sample_stock):
        _buy(db_session, code="600519", price=10.0, quantity=100)
        with patch("app.services.holding_service._get_cached_price", return_value=None):
            summary = holding_service.get_portfolio_summary(db_session)
        assert summary["total_pnl"] is None
        assert summary["total_pnl_pct"] is None

    def test_total_pnl_calculated_when_prices_available(self, db_session: Session, sample_stock):
        _buy(db_session, code="600519", price=10.0, quantity=100)  # cost 1000
        with patch("app.services.holding_service._get_cached_price", return_value=12.0):
            summary = holding_service.get_portfolio_summary(db_session)
        assert summary["total_pnl"] == pytest.approx(200.0)

    def test_no_live_price_falls_back_to_cost(self, db_session: Session, sample_stock, bank_stock):
        _buy(db_session, code="600519", price=100.0, quantity=50)
        _buy(db_session, code="601398", price=5.0, quantity=1000)
        with patch("app.services.holding_service._get_cached_price", return_value=None):
            summary = holding_service.get_portfolio_summary(db_session)
        assert summary["position_count"] == 2
        assert summary["total_cost"] == 10000
        assert summary["total_value"] == 10000
        assert summary["total_pnl"] is None

    def test_with_live_prices(self, db_session: Session, sample_stock):
        _buy(db_session, code="600519", price=100.0, quantity=100)
        with patch("app.services.holding_service._get_cached_price", return_value=120.0):
            summary = holding_service.get_portfolio_summary(db_session)
        assert summary["position_count"] == 1
        assert summary["total_cost"] == 10000
        assert summary["total_value"] == 12000
        assert summary["total_pnl"] == 2000
        assert summary["total_pnl_pct"] == pytest.approx(20.0)

    def test_warnings_for_overweight_position(self, db_session: Session, sample_stock):
        _buy(db_session, code="600519", price=100.0, quantity=100)
        with patch("app.services.holding_service._get_cached_price", return_value=100.0):
            summary = holding_service.get_portfolio_summary(db_session)
        assert any("weight" in w and "20%" in w for w in summary["warnings"])

    def test_industry_concentration_warning(self, db_session: Session, sample_stock, second_stock):
        _buy(db_session, code="600519", price=100.0, quantity=100)
        _buy(db_session, code="000858", price=50.0, quantity=200)
        with patch("app.services.holding_service._get_cached_price", return_value=100.0):
            summary = holding_service.get_portfolio_summary(db_session)
        assert any("Beverage" in w or "行业仓位" in w for w in summary["warnings"])

    def test_fully_sold_excluded(self, db_session: Session, sample_stock):
        _buy(db_session, code="600519", price=100.0, quantity=100)
        _sell(db_session, code="600519", quantity=100, price=110.0)
        with patch("app.services.holding_service._get_cached_price", return_value=110.0):
            summary = holding_service.get_portfolio_summary(db_session)
        assert summary["position_count"] == 0
        assert summary["total_cost"] == 0

    def test_realized_pnl_surfaced(self, db_session: Session, sample_stock):
        """A partial sell leaves an open position carrying realized P&L."""
        _buy(db_session, code="600519", price=100.0, quantity=100)   # cost 10000
        _sell(db_session, code="600519", quantity=40, price=120.0)   # proceeds 4800
        with patch("app.services.holding_service._get_cached_price", return_value=120.0):
            summary = holding_service.get_portfolio_summary(db_session)
        h = summary["holdings"][0]
        assert h["quantity"] == 60
        # realized = 4800 − 100×40 = 800
        assert h["realized_pnl"] == pytest.approx(800.0)


# ===========================================================================
# calculate_rebalancing_guide
# ===========================================================================


class TestCalculateRebalancingGuide:
    def test_empty_portfolio(self, db_session: Session):
        guide = holding_service.calculate_rebalancing_guide(db_session)
        assert guide["holdings"] == []
        assert guide["industry_warnings"] == []
        assert guide["summary"] == "暂无持仓"

    def test_green_signal_strong_performer(self, db_session: Session, sample_stock):
        _buy(db_session, code="600519", price=100.0, quantity=100)
        with patch("app.services.holding_service._get_cached_price", return_value=120.0):
            guide = holding_service.calculate_rebalancing_guide(db_session)
        item = guide["holdings"][0]
        assert item["signal"] == "green"
        assert item["pnl_pct"] == pytest.approx(20.0, abs=0.5)
        assert "强势" in item["suggestion"]

    def test_red_signal_weak_performer(self, db_session: Session, sample_stock):
        old = datetime.now() - timedelta(days=120)
        _buy(db_session, code="600519", price=100.0, quantity=100, when=old)
        with patch("app.services.holding_service._get_cached_price", return_value=80.0):
            guide = holding_service.calculate_rebalancing_guide(db_session)
        item = guide["holdings"][0]
        assert item["signal"] == "red"
        assert item["pnl_pct"] == pytest.approx(-20.0, abs=0.5)
        assert "弱势" in item["suggestion"]

    def test_yellow_signal_neutral(self, db_session: Session, sample_stock):
        _buy(db_session, code="600519", price=100.0, quantity=100)
        with patch("app.services.holding_service._get_cached_price", return_value=105.0):
            guide = holding_service.calculate_rebalancing_guide(db_session)
        item = guide["holdings"][0]
        assert item["signal"] == "yellow"
        assert "中性" in item["suggestion"]

    def test_yellow_signal_when_price_unavailable(self, db_session: Session, sample_stock):
        _buy(db_session, code="600519", price=100.0, quantity=100)
        with patch("app.services.holding_service._get_cached_price", return_value=None):
            guide = holding_service.calculate_rebalancing_guide(db_session)
        item = guide["holdings"][0]
        assert item["signal"] == "yellow"
        assert "手动" in item["suggestion"]

    def test_yellow_signal_short_term_loss(self, db_session: Session, sample_stock):
        recent = datetime.now() - timedelta(days=10)
        _buy(db_session, code="600519", price=100.0, quantity=100, when=recent)
        with patch("app.services.holding_service._get_cached_price", return_value=85.0):
            guide = holding_service.calculate_rebalancing_guide(db_session)
        item = guide["holdings"][0]
        assert item["signal"] == "yellow"
        assert "短期波动" in item["suggestion"]

    def test_industry_warnings(self, db_session: Session, sample_stock, second_stock):
        _buy(db_session, code="600519", price=100.0, quantity=100)
        _buy(db_session, code="000858", price=80.0, quantity=100)
        with patch("app.services.holding_service._get_cached_price", return_value=100.0):
            guide = holding_service.calculate_rebalancing_guide(db_session)
        assert len(guide["industry_warnings"]) > 0

    def test_summary_text_includes_counts(self, db_session: Session, sample_stock, bank_stock):
        _buy(db_session, code="600519", price=100.0, quantity=100)
        old = datetime.now() - timedelta(days=120)
        _buy(db_session, code="601398", price=5.0, quantity=1000, when=old)
        price_map = {"600519": 120.0, "601398": 4.0}
        with patch("app.services.holding_service._get_cached_price", side_effect=price_map.get):
            guide = holding_service.calculate_rebalancing_guide(db_session)
        assert "1 只强势" in guide["summary"]
        assert "1 只弱势" in guide["summary"]
        assert "人之道" in guide["summary"]

    def test_sorted_by_pnl_descending(self, db_session: Session, sample_stock, bank_stock):
        _buy(db_session, code="600519", price=100.0, quantity=100)
        _buy(db_session, code="601398", price=5.0, quantity=1000)
        price_map = {"600519": 120.0, "601398": 4.0}
        with patch("app.services.holding_service._get_cached_price", side_effect=price_map.get):
            guide = holding_service.calculate_rebalancing_guide(db_session)
        pnl_pcts = [h["pnl_pct"] for h in guide["holdings"] if h["pnl_pct"] is not None]
        assert pnl_pcts == sorted(pnl_pcts, reverse=True)
