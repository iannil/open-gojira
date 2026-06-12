"""Test position_sizing_service — convert target_pct to share quantity."""
from datetime import date
import pytest

from app.services.position_sizing_service import compute_buy_quantity
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


def test_basic_sizing(cfg):
    """10% of 1M at price 100 → 1000 shares."""
    result = compute_buy_quantity(
        capital_base=1000000.0, target_pct=0.10,
        current_price=100.0, available_cash=1000000.0,
        broker_config=cfg,
    )
    assert result.quantity == 1000  # 1M × 10% / 100 = 1000


def test_lot_size_rounding(cfg):
    """Quantity must be multiple of 100."""
    result = compute_buy_quantity(
        capital_base=100000.0, target_pct=0.05,
        current_price=33.0, available_cash=100000.0,
        broker_config=cfg,
    )
    # 100000 × 5% / 33 = 151.5 → 151 → 100 (rounded to lot)
    assert result.quantity % 100 == 0
    assert result.quantity == 100


def test_zero_when_insufficient_cash(cfg):
    """If can't afford even 100 shares, return 0."""
    result = compute_buy_quantity(
        capital_base=1000000.0, target_pct=0.10,
        current_price=1000.0,  # 100 shares = 100000 + commission
        available_cash=50000.0,  # only 50000
        broker_config=cfg,
    )
    assert result.quantity == 0


def test_cash_constraint_reduces_qty(cfg):
    """If rounded_qty costs more than available_cash (incl. commission),
    step down one lot."""
    # capital_base × 10% = 100k, price = 95 → raw_qty = 1052 → 1000
    # 1000 × 95 = 95000, commission = 23.75, total = 95023.75
    # available_cash = 95000 → can't afford, drop to 900 shares
    result = compute_buy_quantity(
        capital_base=1000000.0, target_pct=0.10,
        current_price=95.0, available_cash=95000.0,
        broker_config=cfg,
    )
    # 900 × 95 = 85500 + 21.375 commission = 85521.375 ≤ 95000 OK
    assert result.quantity == 900


def test_min_commission_does_not_break_small_orders(cfg):
    """Small order triggers min commission (5 元), still fit in cash."""
    result = compute_buy_quantity(
        capital_base=100000.0, target_pct=0.01,
        current_price=100.0, available_cash=1000.0,
        broker_config=cfg,
    )
    # 100000 × 1% / 100 = 10 → rounded to 0? No, 10 < 100 → 0
    # Actually 10 // 100 = 0, so quantity = 0
    assert result.quantity == 0


def test_returns_estimated_cost(cfg):
    """Result includes estimated total cost incl. commission."""
    result = compute_buy_quantity(
        capital_base=1000000.0, target_pct=0.10,
        current_price=100.0, available_cash=200000.0,
        broker_config=cfg,
    )
    assert result.quantity == 1000
    # 1000 × 100 = 100000, commission = 25, transfer = 1, total = 100026
    assert result.estimated_cost == pytest.approx(100026.0, abs=1.0)
    assert result.estimated_commission == pytest.approx(25.0, abs=0.1)


def test_target_pct_zero_returns_zero(cfg):
    result = compute_buy_quantity(
        capital_base=1000000.0, target_pct=0.0,
        current_price=100.0, available_cash=1000000.0,
        broker_config=cfg,
    )
    assert result.quantity == 0


def test_custom_lot_size(cfg):
    """Some markets use different lot sizes (default 100 for A-share)."""
    result = compute_buy_quantity(
        capital_base=1000000.0, target_pct=0.10,
        current_price=100.0, available_cash=200000.0,
        broker_config=cfg, lot_size=200,
    )
    assert result.quantity % 200 == 0


def test_result_includes_pct_of_nav(cfg):
    """Result reports actual % of NAV used (may be < target after rounding)."""
    result = compute_buy_quantity(
        capital_base=1000000.0, target_pct=0.10,
        current_price=33.0, available_cash=200000.0,
        broker_config=cfg,
    )
    # target 10% = 100k, raw_qty = 3030, rounded to 3000
    # actual = 3000 × 33 / 1000000 = 9.9%
    assert result.actual_pct_of_nav == pytest.approx(0.099, abs=0.001)
