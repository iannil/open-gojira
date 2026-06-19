"""Test holding_risk_rules."""
from datetime import date, datetime
import pytest

from app.models.holding_risk_rule import HoldingRiskRule
from app.services.trade_service import record_trade
from app.models.cash_balance import CashBalance
from app.models.broker_fee_config import BrokerFeeConfig
from app.models.stock import Stock
from app.core.datetime_utils import now


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
    db_session.flush()
    # 建仓
    record_trade(db_session, stock_code="600519", side="BUY",
                 price=100.0, quantity=100,
                 filled_at=datetime(2026, 1, 15, 10, 0), source="manual")
    db_session.flush()


def test_create_risk_rule(db_session, setup):
    rule = HoldingRiskRule(
        stock_code="600519",  # 用 stock_code 作为关联,不是 holding_id(因为 holding 现在是派生的)
        stop_loss_pct=0.08, stop_loss_type="pct_from_cost",
        take_profit_pct=0.30, take_profit_type="pct_from_cost",
        enabled=True,
    )
    db_session.add(rule); db_session.commit()
    assert rule.id is not None
    assert rule.triggered_at is None


def test_risk_rule_default_enabled(db_session, setup):
    rule = HoldingRiskRule(stock_code="600519", stop_loss_pct=0.08,
                            stop_loss_type="pct_from_cost", take_profit_pct=0.30,
                            take_profit_type="pct_from_cost")
    db_session.add(rule); db_session.commit()
    assert rule.enabled is True


def test_risk_rule_triggered_at_set(db_session, setup):
    rule = HoldingRiskRule(stock_code="600519", stop_loss_pct=0.08,
                            stop_loss_type="pct_from_cost", take_profit_pct=0.30,
                            take_profit_type="pct_from_cost")
    db_session.add(rule); db_session.flush()
    rule.triggered_at = now()
    rule.trigger_reason = "Stop loss at -8.5%"
    db_session.commit()
    refreshed = db_session.get(HoldingRiskRule, rule.id)
    assert refreshed.triggered_at is not None
    assert "Stop loss" in refreshed.trigger_reason


def test_risk_rule_trailing_type(db_session, setup):
    """Trailing stop: peak_price tracked."""
    rule = HoldingRiskRule(
        stock_code="600519", stop_loss_pct=0.10, stop_loss_type="trailing",
        take_profit_pct=0.30, take_profit_type="pct_from_cost",
        peak_price=110.0,
    )
    db_session.add(rule); db_session.commit()
    assert rule.peak_price == 110.0
