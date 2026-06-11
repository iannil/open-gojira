"""Tests for holding_service — portfolio management business logic."""

from datetime import date, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.exceptions import EntityNotFound, BusinessRuleViolation
from app.db.base import Base
from app.models.holding import Holding
from app.models.stock import Stock
from app.services import holding_service


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session():
    """Create an in-memory SQLite session with all tables."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def sample_stock(db_session: Session) -> Stock:
    """Insert and return a sample stock."""
    stock = Stock(code="600519", name="Kweichow Moutai", industry="Beverage")
    db_session.add(stock)
    db_session.commit()
    return stock


@pytest.fixture
def second_stock(db_session: Session) -> Stock:
    """Insert and return a second stock (different industry)."""
    stock = Stock(code="000858", name="Wuliangye", industry="Beverage")
    db_session.add(stock)
    db_session.commit()
    return stock


@pytest.fixture
def bank_stock(db_session: Session) -> Stock:
    """Insert and return a bank stock."""
    stock = Stock(code="601398", name="ICBC", industry="Banking")
    db_session.add(stock)
    db_session.commit()
    return stock


def _make_holding_data(stock_code: str = "600519", **overrides) -> dict:
    """Build a holding creation dict with sensible defaults."""
    data = {
        "stock_code": stock_code,
        "buy_date": date(2025, 1, 10),
        "buy_price": 100.0,
        "quantity": 100,
        "stop_profit_price": 130.0,
        "trade_rationale": "Test rationale",
    }
    data.update(overrides)
    return data


# ===========================================================================
# create_holding
# ===========================================================================


class TestCreateHolding:
    def test_success(self, db_session: Session, sample_stock: Stock):
        data = _make_holding_data()
        holding = holding_service.create_holding(db_session, data)

        assert holding.id is not None
        assert holding.stock_code == "600519"
        assert holding.buy_price == 100.0
        assert holding.quantity == 100
        assert holding.stop_profit_price == 130.0

    def test_stock_not_found_raises_404(self, db_session: Session):
        data = _make_holding_data(stock_code="999999")
        with pytest.raises(EntityNotFound) as exc_info:
            holding_service.create_holding(db_session, data)
        assert exc_info.value.entity_type == "Stock"
        assert exc_info.value.identifier == "999999"

    def test_create_preserves_all_fields(self, db_session: Session, sample_stock: Stock):
        data = _make_holding_data(
            buy_date=date(2025, 3, 15),
            buy_price=55.5,
            quantity=200,
            stop_profit_price=70.0,
            trade_rationale="Long-term value play",
        )
        holding = holding_service.create_holding(db_session, data)

        assert holding.buy_date == date(2025, 3, 15)
        assert holding.buy_price == 55.5
        assert holding.quantity == 200
        assert holding.stop_profit_price == 70.0
        assert holding.trade_rationale == "Long-term value play"
        assert holding.sell_date is None
        assert holding.sell_price is None


# ===========================================================================
# sell_holding
# ===========================================================================


class TestSellHolding:
    def test_success(self, db_session: Session, sample_stock: Stock):
        holding = holding_service.create_holding(db_session, _make_holding_data())

        sold = holding_service.sell_holding(
            db_session,
            holding.id,
            sell_date=date(2025, 6, 1),
            sell_price=120.0,
            sell_thesis="Target reached",
        )

        assert sold is not None
        assert sold.sell_date == date(2025, 6, 1)
        assert sold.sell_price == 120.0
        assert sold.sell_thesis == "Target reached"

    def test_not_found_returns_none(self, db_session: Session):
        result = holding_service.sell_holding(
            db_session,
            holding_id=99999,
            sell_date=date(2025, 6, 1),
            sell_price=100.0,
        )
        assert result is None

    def test_sell_without_thesis(self, db_session: Session, sample_stock: Stock):
        holding = holding_service.create_holding(db_session, _make_holding_data())

        sold = holding_service.sell_holding(
            db_session,
            holding.id,
            sell_date=date(2025, 7, 1),
            sell_price=110.0,
        )
        assert sold.sell_thesis is None
        assert sold.sell_price == 110.0


# ===========================================================================
# list_holdings
# ===========================================================================


class TestListHoldings:
    def test_empty_portfolio(self, db_session: Session):
        result = holding_service.list_holdings(db_session)
        assert result == []

    def test_list_all_holdings(self, db_session: Session, sample_stock: Stock, bank_stock: Stock):
        holding_service.create_holding(db_session, _make_holding_data(stock_code="600519"))
        holding_service.create_holding(
            db_session,
            _make_holding_data(
                stock_code="601398",
                buy_date=date(2025, 2, 1),
                buy_price=5.0,
                quantity=1000,
                stop_profit_price=6.0,
            ),
        )

        all_holdings = holding_service.list_holdings(db_session)
        assert len(all_holdings) == 2

    def test_active_only_filter(self, db_session: Session, sample_stock: Stock, bank_stock: Stock):
        h1 = holding_service.create_holding(db_session, _make_holding_data(stock_code="600519"))
        holding_service.create_holding(
            db_session,
            _make_holding_data(stock_code="601398"),
        )

        # Sell one holding
        holding_service.sell_holding(db_session, h1.id, date(2025, 6, 1), 110.0)

        active = holding_service.list_holdings(db_session, active_only=True)
        assert len(active) == 1
        assert active[0].stock_code == "601398"

    def test_ordering_by_buy_date_desc(self, db_session: Session, sample_stock: Stock, second_stock: Stock):
        holding_service.create_holding(
            db_session,
            _make_holding_data(stock_code="600519", buy_date=date(2025, 1, 1)),
        )
        holding_service.create_holding(
            db_session,
            _make_holding_data(stock_code="000858", buy_date=date(2025, 3, 1)),
            force=True,  # both Beverage; bypass 15% industry cap for the test
        )

        holdings = holding_service.list_holdings(db_session)
        assert holdings[0].stock_code == "000858"  # March (later) first
        assert holdings[1].stock_code == "600519"


# ===========================================================================
# get_holding / update_holding / delete_holding
# ===========================================================================


class TestGetUpdateDeleteHolding:
    def test_get_holding_found(self, db_session: Session, sample_stock: Stock):
        holding = holding_service.create_holding(db_session, _make_holding_data())
        result = holding_service.get_holding(db_session, holding.id)
        assert result is not None
        assert result.stock_code == "600519"

    def test_get_holding_not_found(self, db_session: Session):
        result = holding_service.get_holding(db_session, 99999)
        assert result is None

    def test_update_holding(self, db_session: Session, sample_stock: Stock):
        holding = holding_service.create_holding(db_session, _make_holding_data())
        updated = holding_service.update_holding(
            db_session,
            holding.id,
            {"buy_price": 105.0, "quantity": 150},
        )
        assert updated.buy_price == 105.0
        assert updated.quantity == 150

    def test_update_holding_ignores_none_values(self, db_session: Session, sample_stock: Stock):
        holding = holding_service.create_holding(db_session, _make_holding_data(buy_price=100.0))
        updated = holding_service.update_holding(
            db_session,
            holding.id,
            {"buy_price": None, "quantity": 200},
        )
        # buy_price should not change since value is None
        assert updated.buy_price == 100.0
        assert updated.quantity == 200

    def test_update_holding_not_found(self, db_session: Session):
        result = holding_service.update_holding(db_session, 99999, {"buy_price": 50.0})
        assert result is None

    def test_delete_holding(self, db_session: Session, sample_stock: Stock):
        holding = holding_service.create_holding(db_session, _make_holding_data())
        assert holding_service.delete_holding(db_session, holding.id) is True
        assert holding_service.get_holding(db_session, holding.id) is None

    def test_delete_holding_not_found(self, db_session: Session):
        assert holding_service.delete_holding(db_session, 99999) is False


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

    def test_total_pnl_none_when_no_prices(self, db_session: Session):
        """When no prices are available for any holdings, total_pnl should be None."""
        from app.models.stock import Stock

        stock = Stock(code="999999", name="测试", industry="测试")
        db_session.add(stock)
        db_session.commit()

        h = Holding(stock_code="999999", buy_date=date.today(), buy_price=10.0, quantity=100, stop_profit_price=15.0)
        db_session.add(h)
        db_session.commit()

        with patch("app.services.holding_service._get_cached_price", return_value=None):
            summary = holding_service.get_portfolio_summary(db_session)

        assert summary["total_pnl"] is None
        assert summary["total_pnl_pct"] is None

    def test_total_pnl_calculated_when_prices_available(self, db_session: Session):
        """When prices are available, total_pnl should be calculated."""
        from app.models.stock import Stock

        stock = Stock(code="999998", name="测试2", industry="测试")
        db_session.add(stock)
        db_session.commit()

        h = Holding(stock_code="999998", buy_date=date.today(), buy_price=10.0, quantity=100, stop_profit_price=15.0)
        db_session.add(h)
        db_session.commit()

        with patch("app.services.holding_service._get_cached_price", return_value=12.0):
            summary = holding_service.get_portfolio_summary(db_session)

        assert summary["total_pnl"] is not None
        assert summary["total_pnl"] == pytest.approx(200.0)

    def test_with_holdings_no_live_price(self, db_session: Session, sample_stock: Stock, bank_stock: Stock):
        """When live price is unavailable, current_value falls back to buy_price * quantity."""
        holding_service.create_holding(
            db_session,
            _make_holding_data(stock_code="600519", buy_price=100.0, quantity=50),
        )
        holding_service.create_holding(
            db_session,
            _make_holding_data(stock_code="601398", buy_price=5.0, quantity=1000),
        )

        with patch("app.services.holding_service._get_cached_price", return_value=None):
            summary = holding_service.get_portfolio_summary(db_session)

        assert summary["position_count"] == 2
        # total_cost = 100*50 + 5*1000 = 5000 + 5000 = 10000
        assert summary["total_cost"] == 10000
        # With no live price, current_value = buy_price * quantity = same as cost
        assert summary["total_value"] == 10000
        # total_pnl should be None when no prices are available
        assert summary["total_pnl"] is None
        assert summary["total_pnl_pct"] is None

    def test_with_live_prices(self, db_session: Session, sample_stock: Stock):
        holding_service.create_holding(
            db_session,
            _make_holding_data(stock_code="600519", buy_price=100.0, quantity=100),
        )

        with patch("app.services.holding_service._get_cached_price", return_value=120.0):
            summary = holding_service.get_portfolio_summary(db_session)

        assert summary["position_count"] == 1
        assert summary["total_cost"] == 10000
        assert summary["total_value"] == 12000
        assert summary["total_pnl"] == 2000
        assert summary["total_pnl_pct"] == pytest.approx(20.0)

    def test_warnings_for_overweight_position(self, db_session: Session, sample_stock: Stock):
        """A single holding gets 100% weight, which exceeds 20% threshold."""
        holding_service.create_holding(
            db_session,
            _make_holding_data(stock_code="600519", buy_price=100.0, quantity=100),
        )

        with patch("app.services.holding_service._get_cached_price", return_value=100.0):
            summary = holding_service.get_portfolio_summary(db_session)

        # 100% weight > 20% threshold should generate a warning
        assert any("weight" in w and "20%" in w for w in summary["warnings"])

    def test_industry_concentration_warning(self, db_session: Session, sample_stock: Stock, second_stock: Stock):
        """Two stocks in the same industry with high total weight."""
        holding_service.create_holding(
            db_session,
            _make_holding_data(stock_code="600519", buy_price=100.0, quantity=100),
        )
        holding_service.create_holding(
            db_session,
            _make_holding_data(stock_code="000858", buy_price=50.0, quantity=200),
            force=True,
        )

        with patch("app.services.holding_service._get_cached_price", return_value=100.0):
            summary = holding_service.get_portfolio_summary(db_session)

        # Both Beverage stocks: industry weight exceeds 15%
        assert any("Beverage" in w or "行业仓位" in w for w in summary["warnings"])

    def test_stop_profit_alert(self, db_session: Session, sample_stock: Stock):
        """When current price >= stop_profit_price, a stop-profit alert should fire."""
        holding_service.create_holding(
            db_session,
            _make_holding_data(
                stock_code="600519",
                buy_price=100.0,
                quantity=100,
                stop_profit_price=110.0,
            ),
        )

        # Current price 115 >= stop_profit_price 110
        with patch("app.services.holding_service._get_cached_price", return_value=115.0):
            summary = holding_service.get_portfolio_summary(db_session)

        assert any("止盈" in w for w in summary["warnings"])

    def test_no_stop_profit_alert_below_threshold(self, db_session: Session, sample_stock: Stock):
        holding_service.create_holding(
            db_session,
            _make_holding_data(
                stock_code="600519",
                buy_price=100.0,
                quantity=100,
                stop_profit_price=130.0,
            ),
        )

        with patch("app.services.holding_service._get_cached_price", return_value=105.0):
            summary = holding_service.get_portfolio_summary(db_session)

        assert not any("止盈" in w for w in summary["warnings"])

    def test_sold_holdings_excluded(self, db_session: Session, sample_stock: Stock):
        h = holding_service.create_holding(
            db_session,
            _make_holding_data(stock_code="600519", buy_price=100.0, quantity=100),
        )
        holding_service.sell_holding(db_session, h.id, date(2025, 6, 1), 110.0)

        with patch("app.services.holding_service._get_cached_price", return_value=110.0):
            summary = holding_service.get_portfolio_summary(db_session)

        assert summary["position_count"] == 0
        assert summary["total_cost"] == 0


# ===========================================================================
# calculate_rebalancing_guide
# ===========================================================================


class TestCalculateRebalancingGuide:
    def test_empty_portfolio(self, db_session: Session):
        guide = holding_service.calculate_rebalancing_guide(db_session)
        assert guide["holdings"] == []
        assert guide["industry_warnings"] == []
        assert guide["summary"] == "暂无持仓"

    def test_green_signal_strong_performer(self, db_session: Session, sample_stock: Stock):
        """pnl_pct >= 15% should get a green signal."""
        holding_service.create_holding(
            db_session,
            _make_holding_data(stock_code="600519", buy_price=100.0, quantity=100),
        )

        # Price 120 => pnl_pct = 20%
        with patch("app.services.holding_service._get_cached_price", return_value=120.0):
            guide = holding_service.calculate_rebalancing_guide(db_session)

        assert len(guide["holdings"]) == 1
        item = guide["holdings"][0]
        assert item["signal"] == "green"
        assert item["pnl_pct"] == pytest.approx(20.0, abs=0.5)
        assert "强势" in item["suggestion"]

    def test_red_signal_weak_performer(self, db_session: Session, sample_stock: Stock):
        """pnl_pct < -10% held > 30 days should get a red signal."""
        old_date = date.today() - timedelta(days=120)
        holding_service.create_holding(
            db_session,
            _make_holding_data(stock_code="600519", buy_price=100.0, quantity=100, buy_date=old_date),
        )

        # Price 80 => pnl_pct = -20%
        with patch("app.services.holding_service._get_cached_price", return_value=80.0):
            guide = holding_service.calculate_rebalancing_guide(db_session)

        item = guide["holdings"][0]
        assert item["signal"] == "red"
        assert item["pnl_pct"] == pytest.approx(-20.0, abs=0.5)
        assert "弱势" in item["suggestion"]

    def test_yellow_signal_neutral(self, db_session: Session, sample_stock: Stock):
        """-10% <= pnl_pct < 15% should get a yellow signal."""
        holding_service.create_holding(
            db_session,
            _make_holding_data(stock_code="600519", buy_price=100.0, quantity=100),
        )

        # Price 105 => pnl_pct = 5%
        with patch("app.services.holding_service._get_cached_price", return_value=105.0):
            guide = holding_service.calculate_rebalancing_guide(db_session)

        item = guide["holdings"][0]
        assert item["signal"] == "yellow"
        assert "中性" in item["suggestion"]

    def test_yellow_signal_when_price_unavailable(self, db_session: Session, sample_stock: Stock):
        """When live price is unavailable, signal should be yellow with manual evaluation note."""
        holding_service.create_holding(
            db_session,
            _make_holding_data(stock_code="600519", buy_price=100.0, quantity=100),
        )

        with patch("app.services.holding_service._get_cached_price", return_value=None):
            guide = holding_service.calculate_rebalancing_guide(db_session)

        item = guide["holdings"][0]
        assert item["signal"] == "yellow"
        assert "手动" in item["suggestion"]

    def test_yellow_signal_short_term_loss(self, db_session: Session, sample_stock: Stock):
        """Loss > 10% but held < 30 days => yellow (short-term fluctuation)."""
        recent_date = date.today() - timedelta(days=10)
        holding_service.create_holding(
            db_session,
            _make_holding_data(stock_code="600519", buy_price=100.0, quantity=100, buy_date=recent_date),
        )

        with patch("app.services.holding_service._get_cached_price", return_value=85.0):
            guide = holding_service.calculate_rebalancing_guide(db_session)

        item = guide["holdings"][0]
        assert item["signal"] == "yellow"
        assert "短期波动" in item["suggestion"]

    def test_industry_warnings(self, db_session: Session, sample_stock: Stock, second_stock: Stock):
        """Two stocks in the same industry exceeding 15% weight should trigger warning."""
        holding_service.create_holding(
            db_session,
            _make_holding_data(stock_code="600519", buy_price=100.0, quantity=100),
        )
        holding_service.create_holding(
            db_session,
            _make_holding_data(stock_code="000858", buy_price=80.0, quantity=100),
            force=True,
        )

        with patch("app.services.holding_service._get_cached_price", return_value=100.0):
            guide = holding_service.calculate_rebalancing_guide(db_session)

        assert len(guide["industry_warnings"]) > 0

    def test_summary_text_includes_counts(self, db_session: Session, sample_stock: Stock, bank_stock: Stock):
        holding_service.create_holding(
            db_session,
            _make_holding_data(stock_code="600519", buy_price=100.0, quantity=100),
        )
        old_date = date.today() - timedelta(days=120)
        holding_service.create_holding(
            db_session,
            _make_holding_data(stock_code="601398", buy_price=5.0, quantity=1000, buy_date=old_date),
        )

        price_map = {"600519": 120.0, "601398": 4.0}

        def mock_price(code):
            return price_map.get(code)

        with patch("app.services.holding_service._get_cached_price", side_effect=mock_price):
            guide = holding_service.calculate_rebalancing_guide(db_session)

        assert "1 只强势" in guide["summary"]
        assert "1 只弱势" in guide["summary"]
        assert "人之道" in guide["summary"]

    def test_sorted_by_pnl_descending(self, db_session: Session, sample_stock: Stock, bank_stock: Stock):
        holding_service.create_holding(
            db_session,
            _make_holding_data(stock_code="600519", buy_price=100.0, quantity=100),
        )
        holding_service.create_holding(
            db_session,
            _make_holding_data(stock_code="601398", buy_price=5.0, quantity=1000),
        )

        price_map = {"600519": 120.0, "601398": 4.0}

        def mock_price(code):
            return price_map.get(code)

        with patch("app.services.holding_service._get_cached_price", side_effect=mock_price):
            guide = holding_service.calculate_rebalancing_guide(db_session)

        pnl_pcts = [h["pnl_pct"] for h in guide["holdings"] if h["pnl_pct"] is not None]
        assert pnl_pcts == sorted(pnl_pcts, reverse=True)
