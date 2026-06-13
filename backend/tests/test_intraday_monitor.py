"""Test intraday_monitor_service — poll_once orchestration."""
from datetime import date, datetime
from unittest.mock import patch
import pytest

from app.models.broker_fee_config import BrokerFeeConfig
from app.models.cash_balance import CashBalance
from app.models.holding_risk_rule import HoldingRiskRule
from app.models.stock import Stock
from app.models.trade import Trade
from app.models.watchlist import WatchlistGroup, WatchlistItem
from app.services.trade_service import record_trade
from app.services.intraday_monitor_service import (
    intraday_watch_list, poll_once, PollResult,
)


@pytest.fixture
def setup(db_session):
    db_session.add(Stock(code="600519", name="贵州茅台", exchange="sh",
                          listing_status="normally_listed", prev_close=100.0))
    db_session.add(Stock(code="000001", name="平安银行", exchange="sz",
                          listing_status="normally_listed", prev_close=15.0))
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
    # Add 000001 to watchlist (the other source intraday_watch_list unions over)
    db_session.add(WatchlistGroup(id=1, name="default"))
    db_session.add(WatchlistItem(group_id=1, stock_code="000001"))
    db_session.flush()


def test_intraday_watch_list_includes_holdings(db_session, setup):
    codes = intraday_watch_list(db_session)
    assert "600519" in codes  # held
    assert "000001" in codes  # in watchlist


def test_poll_once_no_rules_no_events(db_session, setup):
    """Basic poll: no rules → no events but prices fetched."""
    with patch("app.services.intraday_monitor_service.get_realtime_prices") as grp:
        grp.return_value = {
            "600519": {"name": "茅台", "current": 100, "prev_close": 100,
                       "high": 101, "low": 99},
            "000001": {"name": "平安", "current": 15, "prev_close": 15,
                       "high": 15.5, "low": 14.8},
        }
        result = poll_once(db_session)
    assert isinstance(result, PollResult)
    assert result.codes_checked >= 1
    assert len(result.stop_loss_events) == 0


def test_poll_once_triggers_stop_loss(db_session, setup):
    db_session.add(HoldingRiskRule(
        stock_code="600519", stop_loss_pct=0.05,
        stop_loss_type="pct_from_cost",
        take_profit_pct=0.50, take_profit_type="pct_from_cost",
    ))
    db_session.flush()
    with patch("app.services.intraday_monitor_service.get_realtime_prices") as grp:
        grp.return_value = {
            "600519": {"name": "茅台", "current": 90, "prev_close": 100,
                       "high": 100, "low": 89},
            "000001": {"name": "平安", "current": 15, "prev_close": 15,
                       "high": 15, "low": 15},
        }
        result = poll_once(db_session)
    assert len(result.stop_loss_events) == 1
    assert result.stop_loss_events[0].stock_code == "600519"


def test_poll_once_handles_realtime_failure(db_session, setup):
    """Network failure → empty result, no exception."""
    with patch("app.services.intraday_monitor_service.get_realtime_prices") as grp:
        grp.return_value = {}  # network failure
        result = poll_once(db_session)
    assert result.codes_checked >= 1
    assert len(result.stop_loss_events) == 0
