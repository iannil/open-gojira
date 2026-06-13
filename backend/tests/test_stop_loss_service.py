"""Test stop_loss_service — rule evaluation + trigger."""
from datetime import date, datetime
import pytest

from app.models.broker_fee_config import BrokerFeeConfig
from app.models.cash_balance import CashBalance
from app.models.holding_risk_rule import HoldingRiskRule
from app.models.stock import Stock
from app.models.trade import Trade
from app.services.trade_service import record_trade
from app.services.stop_loss_service import (
    check_holding, StopLossEvent, TakeProfitEvent,
)


@pytest.fixture
def setup(db_session):
    db_session.add(Stock(code="600519", name="贵州茅台", exchange="sh",
                          listing_status="normally_listed", prev_close=100.0))
    db_session.add(CashBalance(id=1, balance=1000000.0))
    db_session.add(BrokerFeeConfig(
        broker_name="default", commission_rate=0.00025, commission_min=5.0,
        stamp_duty_rate=0.0005, transfer_fee_rate=0.00001,
        effective_from=date(2023, 10, 23), is_active=True,
    ))
    db_session.flush()  # ensure Stock visible to record_trade's db.get()
    record_trade(db_session, stock_code="600519", side="BUY",
                 price=100.0, quantity=100,
                 filled_at=datetime(2026, 6, 11, 10, 0), source="manual")
    db_session.flush()


def test_no_rule_no_event(db_session, setup):
    """No risk rule defined → no event."""
    event = check_holding(db_session, "600519", current_price=80.0)
    assert event is None


def test_stop_loss_triggers(db_session, setup):
    """Price drops below -8% → stop loss event."""
    db_session.add(HoldingRiskRule(
        stock_code="600519", stop_loss_pct=0.08,
        stop_loss_type="pct_from_cost",
        take_profit_pct=0.30, take_profit_type="pct_from_cost",
    ))
    db_session.flush()
    # Cost basis ~100, current 91 → -9% < -8% threshold
    event = check_holding(db_session, "600519", current_price=91.0)
    assert event is not None
    assert isinstance(event, StopLossEvent)
    assert event.stock_code == "600519"
    assert event.current_price == 91.0


def test_stop_loss_not_triggered_above_threshold(db_session, setup):
    db_session.add(HoldingRiskRule(
        stock_code="600519", stop_loss_pct=0.08,
        stop_loss_type="pct_from_cost",
        take_profit_pct=0.30, take_profit_type="pct_from_cost",
    ))
    db_session.flush()
    # -5% > -8%, no trigger
    event = check_holding(db_session, "600519", current_price=95.0)
    # Take profit also not triggered (95/100 - 1 = -5%, < 30%)
    assert event is None


def test_take_profit_triggers(db_session, setup):
    db_session.add(HoldingRiskRule(
        stock_code="600519", stop_loss_pct=0.08,
        stop_loss_type="pct_from_cost",
        take_profit_pct=0.30, take_profit_type="pct_from_cost",
    ))
    db_session.flush()
    # +35% > +30% threshold
    event = check_holding(db_session, "600519", current_price=135.0)
    assert event is not None
    assert isinstance(event, TakeProfitEvent)


def test_disabled_rule_skipped(db_session, setup):
    db_session.add(HoldingRiskRule(
        stock_code="600519", stop_loss_pct=0.08,
        stop_loss_type="pct_from_cost",
        take_profit_pct=0.30, take_profit_type="pct_from_cost",
        enabled=False,
    ))
    db_session.flush()
    event = check_holding(db_session, "600519", current_price=80.0)
    assert event is None


def test_already_triggered_skipped(db_session, setup):
    db_session.add(HoldingRiskRule(
        stock_code="600519", stop_loss_pct=0.08,
        stop_loss_type="pct_from_cost",
        take_profit_pct=0.30, take_profit_type="pct_from_cost",
        triggered_at=datetime(2026, 6, 12, 10, 0),
    ))
    db_session.flush()
    event = check_holding(db_session, "600519", current_price=80.0)
    assert event is None


def test_trailing_stop_loss(db_session, setup):
    """Trailing: drops 10% from peak."""
    db_session.add(HoldingRiskRule(
        stock_code="600519",
        stop_loss_pct=0.10, stop_loss_type="trailing",
        peak_price=120.0,  # peak was 120
        take_profit_pct=0.50, take_profit_type="pct_from_cost",
    ))
    db_session.flush()
    # Current 107 < 120 × 0.9 = 108 → trigger
    event = check_holding(db_session, "600519", current_price=107.0)
    assert event is not None
    assert isinstance(event, StopLossEvent)


def test_trailing_updates_peak_on_increase(db_session, setup):
    """If current > peak, peak_price should update."""
    db_session.add(HoldingRiskRule(
        stock_code="600519",
        stop_loss_pct=0.10, stop_loss_type="trailing",
        peak_price=110.0,  # existing peak
        take_profit_pct=0.50, take_profit_type="pct_from_cost",
    ))
    db_session.flush()
    # current 120 > 110, should update peak to 120 (no trigger)
    event = check_holding(db_session, "600519", current_price=120.0)
    assert event is None
    refreshed = db_session.query(HoldingRiskRule).filter_by(stock_code="600519").one()
    assert refreshed.peak_price == 120.0


def test_no_holding_skips(db_session, setup):
    """No position → no check needed."""
    db_session.add(HoldingRiskRule(
        stock_code="600519", stop_loss_pct=0.08,
        stop_loss_type="pct_from_cost",
        take_profit_pct=0.30, take_profit_type="pct_from_cost",
    ))
    # Delete the holding
    db_session.query(Trade).delete()
    db_session.flush()
    event = check_holding(db_session, "600519", current_price=80.0)
    assert event is None
