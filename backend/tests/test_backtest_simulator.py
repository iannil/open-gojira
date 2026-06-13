"""Test backtest_simulator — T+1 / lot / band / slippage / fees."""
from datetime import date
import pytest

from app.services.backtest_simulator import (
    simulate_buy, simulate_sell, PortfolioState,
    can_sell_today, apply_dividend,
)
from app.models.broker_fee_config import BrokerFeeConfig


@pytest.fixture
def cfg(db_session):
    c = BrokerFeeConfig(
        broker_name="default", commission_rate=0.00025, commission_min=5.0,
        stamp_duty_rate=0.0005, transfer_fee_rate=0.00001,
        effective_from=date(2023, 10, 23), is_active=True,
    )
    db_session.add(c); db_session.flush()
    return c


def _kline(open_, high, low, close):
    return {"open": open_, "high": high, "low": low, "close": close, "date": "2024-01-02"}


# --- PortfolioState ---

def test_portfolio_state_initial():
    p = PortfolioState(cash=1000000.0)
    assert p.cash == 1000000.0
    assert p.positions == {}
    assert p.realized_pnl == 0.0


def test_portfolio_state_buy_creates_position(cfg):
    p = PortfolioState(cash=1000000.0)
    result = simulate_buy(
        portfolio=p, stock_code="600519",
        target_price=100.0, quantity=100,
        kline=_kline(99, 101, 98, 100),
        broker_config=cfg, slippage_bps=10,
        exchange="sh", listing_status="normally_listed",
    )
    assert result.success
    assert result.filled_quantity == 100
    assert result.filled_price == pytest.approx(100.1, abs=0.01)  # 100 × (1 + 0.001)
    assert "600519" in p.positions
    assert p.positions["600519"].quantity == 100
    # cash decreased
    assert p.cash < 1000000.0


def test_portfolio_state_buy_insufficient_cash_fails(cfg):
    p = PortfolioState(cash=1000.0)  # only 1000
    result = simulate_buy(
        portfolio=p, stock_code="600519",
        target_price=100.0, quantity=100,
        kline=_kline(99, 101, 98, 100),
        broker_config=cfg, slippage_bps=10,
        exchange="sh", listing_status="normally_listed",
    )
    assert not result.success
    assert "cash" in result.reason.lower() or "insufficient" in result.reason.lower()


def test_portfolio_state_buy_rounds_to_lot(cfg):
    """Quantity must be multiple of 100."""
    p = PortfolioState(cash=1000000.0)
    result = simulate_buy(
        portfolio=p, stock_code="600519",
        target_price=100.0, quantity=150,  # not multiple of 100
        kline=_kline(99, 101, 98, 100),
        broker_config=cfg, slippage_bps=10,
        exchange="sh", listing_status="normally_listed",
    )
    assert result.success
    assert result.filled_quantity == 100  # rounded down


# --- 涨跌停 ---

def test_buy_above_upper_limit_rejected(cfg):
    """target_price > kline.high → assume 涨停, reject BUY."""
    p = PortfolioState(cash=1000000.0)
    result = simulate_buy(
        portfolio=p, stock_code="600519",
        target_price=120.0, quantity=100,  # way above kline.high=101
        kline=_kline(99, 101, 98, 100),
        broker_config=cfg, slippage_bps=10,
        exchange="sh", listing_status="normally_listed",
    )
    assert not result.success
    assert "limit" in result.reason.lower() or "band" in result.reason.lower()


def test_sell_below_lower_limit_rejected(cfg):
    """target_price < kline.low → assume 跌停, reject SELL."""
    p = PortfolioState(cash=1000000.0, positions={"600519": {"quantity": 100, "avg_cost": 100}})
    result = simulate_sell(
        portfolio=p, stock_code="600519",
        target_price=80.0, quantity=100,
        kline=_kline(99, 101, 98, 100),
        broker_config=cfg, slippage_bps=10,
        exchange="sh", listing_status="normally_listed",
    )
    assert not result.success


# --- T+1 ---

def test_t_plus_1_blocks_same_day_sell():
    """今日 BUY 不能今日 SELL."""
    p = PortfolioState(cash=1000000.0)
    # 模拟今日买入
    p.positions["600519"] = {"quantity": 100, "avg_cost": 100, "buy_date": date(2024, 1, 2)}
    assert not can_sell_today(p, "600519", date(2024, 1, 2))


def test_t_plus_1_allows_next_day_sell():
    p = PortfolioState(cash=1000000.0)
    p.positions["600519"] = {"quantity": 100, "avg_cost": 100, "buy_date": date(2024, 1, 2)}
    assert can_sell_today(p, "600519", date(2024, 1, 3))


# --- SELL ---

def test_sell_reduces_position(cfg):
    p = PortfolioState(cash=1000000.0,
                        positions={"600519": {"quantity": 200, "avg_cost": 100, "buy_date": date(2024, 1, 1)}})
    result = simulate_sell(
        portfolio=p, stock_code="600519",
        target_price=110.0, quantity=100,
        kline=_kline(109, 111, 108, 110),
        broker_config=cfg, slippage_bps=10,
        exchange="sh", listing_status="normally_listed",
        today=date(2024, 1, 2),
    )
    assert result.success
    assert p.positions["600519"]["quantity"] == 100
    # cash increased
    assert p.cash > 1000000.0


def test_sell_zero_position_fails(cfg):
    p = PortfolioState(cash=1000000.0)
    result = simulate_sell(
        portfolio=p, stock_code="600519",
        target_price=110.0, quantity=100,
        kline=_kline(109, 111, 108, 110),
        broker_config=cfg, slippage_bps=10,
        exchange="sh", listing_status="normally_listed",
        today=date(2024, 1, 2),
    )
    assert not result.success


def test_sell_more_than_held_fails(cfg):
    p = PortfolioState(cash=1000000.0,
                        positions={"600519": {"quantity": 50, "avg_cost": 100, "buy_date": date(2024, 1, 1)}})
    result = simulate_sell(
        portfolio=p, stock_code="600519",
        target_price=110.0, quantity=100,
        kline=_kline(109, 111, 108, 110),
        broker_config=cfg, slippage_bps=10,
        exchange="sh", listing_status="normally_listed",
        today=date(2024, 1, 2),
    )
    assert not result.success


# --- DIVIDEND ---

def test_apply_dividend_adds_cash():
    """Cash dividend: per_share × qty_held added to cash."""
    p = PortfolioState(cash=1000000.0,
                        positions={"600519": {"quantity": 100, "avg_cost": 100, "buy_date": date(2024, 1, 1)}})
    apply_dividend(portfolio=p, stock_code="600519", per_share=5.0)
    assert p.cash == 1000000.0 + 500.0


def test_apply_dividend_no_position_noop():
    p = PortfolioState(cash=1000000.0)
    apply_dividend(portfolio=p, stock_code="600519", per_share=5.0)
    assert p.cash == 1000000.0


# --- Stock dividend / capitalization ---

def test_apply_stock_dividend_increases_quantity():
    """10送5: 100股 → 150股."""
    from app.services.backtest_simulator import apply_stock_dividend
    p = PortfolioState(cash=1000000.0,
                        positions={"600519": {"quantity": 100, "avg_cost": 100, "buy_date": date(2024, 1, 1)}})
    apply_stock_dividend(portfolio=p, stock_code="600519", per_10_shares=5.0)
    assert p.positions["600519"]["quantity"] == 150


def test_apply_capitalization_increases_quantity():
    from app.services.backtest_simulator import apply_capitalization
    p = PortfolioState(cash=1000000.0,
                        positions={"600519": {"quantity": 100, "avg_cost": 100, "buy_date": date(2024, 1, 1)}})
    apply_capitalization(portfolio=p, stock_code="600519", per_10_shares=10.0)
    assert p.positions["600519"]["quantity"] == 200


# --- Slippage ---

def test_slippage_zero_for_backtest_purity(cfg):
    """Slippage can be set to 0 for theoretical backtest."""
    p = PortfolioState(cash=1000000.0)
    result = simulate_buy(
        portfolio=p, stock_code="600519",
        target_price=100.0, quantity=100,
        kline=_kline(99, 101, 98, 100),
        broker_config=cfg, slippage_bps=0,
        exchange="sh", listing_status="normally_listed",
    )
    assert result.filled_price == 100.0  # exact


def test_slippage_higher_for_pessimistic(cfg):
    """50bps slippage simulates harder-to-fill orders."""
    p = PortfolioState(cash=1000000.0)
    result = simulate_buy(
        portfolio=p, stock_code="600519",
        target_price=100.0, quantity=100,
        kline=_kline(99, 101, 98, 100),
        broker_config=cfg, slippage_bps=50,
        exchange="sh", listing_status="normally_listed",
    )
    assert result.filled_price == pytest.approx(100.5, abs=0.01)
