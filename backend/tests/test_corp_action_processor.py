"""Test corp_action_processor_service — apply rules to holdings/trades."""
from datetime import date, datetime
import pytest

from app.models.corp_action import CorpAction
from app.models.cash_balance import CashBalance
from app.models.broker_fee_config import BrokerFeeConfig
from app.models.stock import Stock
from app.models.trade import Trade
from app.services.trade_service import record_trade
from app.services.corp_action_processor_service import (
    process_pending_corp_actions, process_one,
    _apply_cash_dividend, _apply_stock_dividend, _apply_capitalization,
    _apply_delist, _apply_merger, _apply_rights_issue,
)


def _add_holding(db, code, quantity, buy_price=100.0):
    """v2: corp actions read qty_held from Holding (positions come from CSV,
    not BUY trades — no trade->holding sync)."""
    from app.models.holding import Holding
    db.add(Holding(
        stock_code=code, buy_date=date(2008, 1, 1), buy_price=buy_price,
        quantity=quantity, stop_profit_price=buy_price * 1.3,
    ))
    db.flush()


@pytest.fixture
def setup(db_session):
    db_session.add(Stock(code="600519", name="贵州茅台", exchange="sh",
                          listing_status="normally_listed", prev_close=100.0))
    db_session.add(Stock(code="600432", name="退市吉恩", exchange="sh",
                          listing_status="normally_listed", prev_close=5.0))
    db_session.add(CashBalance(id=1, balance=100000.0))
    # Modern fee config (covers 2026 trades)
    db_session.add(BrokerFeeConfig(
        broker_name="default", commission_rate=0.00025, commission_min=5.0,
        stamp_duty_rate=0.0005, transfer_fee_rate=0.00001,
        effective_from=date(2023, 10, 23), is_active=True,
    ))
    # Legacy fee config (covers historical merger test — 2008 BUY)
    db_session.add(BrokerFeeConfig(
        broker_name="legacy", commission_rate=0.0003, commission_min=5.0,
        stamp_duty_rate=0.001, transfer_fee_rate=0.00001,
        effective_from=date(2000, 1, 1), is_active=True,
    ))
    db_session.flush()


# --- cash_dividend ---

def test_apply_cash_dividend_creates_dividend_trade(db_session, setup):
    """Cash dividend: 持仓 N 股,每股派 X 元 → DIVIDEND trade."""
    # 持有 100 股
    record_trade(db_session, stock_code="600519", side="BUY",
                 price=100.0, quantity=100,
                 filled_at=datetime(2026, 1, 15, 10, 0), source="manual")
    db_session.flush()
    _add_holding(db_session, "600519", 100)  # v2: position from Holding
    balance_before_div = db_session.query(CashBalance).first().balance
    # 创建 corp_action:每股派 25
    ca = CorpAction(
        stock_code="600519", ex_date=date(2026, 7, 15),
        action_type="cash_dividend",
        params_json={"per_share": 25.0},
        source="lixinger",
    )
    db_session.add(ca); db_session.flush()

    result = process_one(db_session, ca)
    db_session.commit()

    assert result.applied_trade_id is not None
    t = db_session.get(Trade, result.applied_trade_id)
    assert t.side == "DIVIDEND"
    assert t.price == 0
    assert t.quantity == 0
    # cash inflow: 100 股 × 25 元 = 2500 元 → total_value = -2500(负数表示流入)
    assert t.total_value == -2500.0
    # cash_balance += 2500(从 BUY 后的余额再 +2500)
    cb = db_session.query(CashBalance).first()
    assert cb.balance == pytest.approx(balance_before_div + 2500.0, abs=0.01)
    # processed_at set
    assert result.processed_at is not None


def test_apply_cash_dividend_no_holding_skips(db_session, setup):
    """If we don't hold the stock, dividend has no effect — skip."""
    ca = CorpAction(
        stock_code="600519", ex_date=date(2026, 7, 15),
        action_type="cash_dividend",
        params_json={"per_share": 25.0},
        source="lixinger",
    )
    db_session.add(ca); db_session.flush()
    result = process_one(db_session, ca)
    db_session.commit()
    # processed but no trade
    assert result.processed_at is not None
    assert result.applied_trade_id is None
    # cash 不变
    assert db_session.query(CashBalance).first().balance == 100000.0


# --- stock_dividend ---

def test_apply_stock_dividend(db_session, setup):
    """10送5: 持 100 股 → 持 150 股."""
    record_trade(db_session, stock_code="600519", side="BUY",
                 price=100.0, quantity=100,
                 filled_at=datetime(2026, 1, 15, 10, 0), source="manual")
    db_session.flush()
    _add_holding(db_session, "600519", 100)  # v2: position from Holding
    ca = CorpAction(
        stock_code="600519", ex_date=date(2026, 7, 15),
        action_type="stock_dividend",
        params_json={"per_10_shares": 5.0},
        source="lixinger",
    )
    db_session.add(ca); db_session.flush()
    process_one(db_session, ca)
    db_session.commit()

    t = db_session.query(Trade).filter(Trade.side == "CORP_ACTION").one()
    # 100 股 × 5/10 = 50 股
    assert t.quantity == 50
    assert t.price == 0
    assert t.total_value == 0


def test_apply_capitalization(db_session, setup):
    """10转10: 持 200 股 → 持 400 股."""
    record_trade(db_session, stock_code="600519", side="BUY",
                 price=100.0, quantity=200,
                 filled_at=datetime(2026, 1, 15, 10, 0), source="manual")
    db_session.flush()
    _add_holding(db_session, "600519", 200)  # v2: position from Holding
    ca = CorpAction(
        stock_code="600519", ex_date=date(2026, 7, 15),
        action_type="capitalization",
        params_json={"per_10_shares": 10.0},
        source="lixinger",
    )
    db_session.add(ca); db_session.flush()
    process_one(db_session, ca)
    db_session.commit()
    t = db_session.query(Trade).filter(Trade.side == "CORP_ACTION").one()
    assert t.quantity == 200  # 200 × 10/10


# --- delist ---

def test_apply_delist_marks_stock(db_session, setup):
    """Delist: update Stock.listing_status to delisting_transitional_period."""
    ca = CorpAction(
        stock_code="600432", ex_date=date(2018, 7, 11),
        action_type="delist",
        params_json={"new_name": "退市吉恩"},
        source="heuristic",
    )
    db_session.add(ca); db_session.flush()
    process_one(db_session, ca)
    db_session.commit()
    s = db_session.get(Stock, "600432")
    assert s.listing_status == "delisting_transitional_period"
    # no trade created
    assert db_session.query(Trade).count() == 0


# --- rights_issue (skip + alert) ---

def test_apply_rights_issue_emits_alert_and_skips(db_session, setup):
    """Rights issue: don't auto-apply, emit warning alert."""
    record_trade(db_session, stock_code="600519", side="BUY",
                 price=100.0, quantity=100,
                 filled_at=datetime(2026, 1, 15, 10, 0), source="manual")
    db_session.flush()
    _add_holding(db_session, "600519", 100)  # v2: position from Holding
    ca = CorpAction(
        stock_code="600519", ex_date=date(2026, 7, 15),
        action_type="rights_issue",
        params_json={"per_10_shares": 3, "subscription_price": 80.0,
                     "subscription_end": "2026-07-01"},
        source="manual",
    )
    db_session.add(ca); db_session.flush()
    process_one(db_session, ca)
    db_session.commit()

    from app.services.system_alert_service import list_unresolved
    alerts = list_unresolved(db_session, category="data")
    # 应该有配股 alert
    rights_alerts = [a for a in alerts if "配股" in a.message or "rights" in a.message.lower()]
    assert len(rights_alerts) >= 1
    # processed_at 设了(不重复触发)
    assert ca.processed_at is not None


# --- merger ---

def test_apply_merger(db_session, setup):
    """Merger: convert old code to new at ratio."""
    db_session.add(Stock(code="600001", name="邯郸钢铁", exchange="sh",
                          listing_status="normally_listed", prev_close=10.0))
    db_session.add(Stock(code="600019", name="宝钢股份", exchange="sh",
                          listing_status="normally_listed", prev_close=15.0))
    db_session.flush()
    record_trade(db_session, stock_code="600001", side="BUY",
                 price=10.0, quantity=1000,
                 filled_at=datetime(2008, 1, 1, 10, 0), source="manual")
    db_session.flush()
    _add_holding(db_session, "600001", 1000, buy_price=10.0)  # v2: position from Holding
    ca = CorpAction(
        stock_code="600001", ex_date=date(2008, 6, 1),
        action_type="merger",
        params_json={"new_code": "600019", "ratio": 0.8},
        source="manual",
    )
    db_session.add(ca); db_session.flush()
    process_one(db_session, ca)
    db_session.commit()
    # 旧 code 1000 股 → SELL(-1000); 新 code 800 股 → BUY(+800)
    trades = db_session.query(Trade).filter(Trade.source == "corp_action").all()
    assert len(trades) == 2
    # check quantities
    sell_qty = sum(t.quantity for t in trades if t.side == "SELL")
    buy_qty = sum(t.quantity for t in trades if t.side == "BUY")
    assert sell_qty == -1000
    assert buy_qty == 800  # 1000 × 0.8


# --- batch processing ---

def test_process_pending(db_session, setup):
    """Process all pending corp_actions."""
    record_trade(db_session, stock_code="600519", side="BUY",
                 price=100.0, quantity=100,
                 filled_at=datetime(2026, 1, 15, 10, 0), source="manual")
    db_session.add(CorpAction(
        stock_code="600519", ex_date=date(2026, 7, 15),
        action_type="cash_dividend", params_json={"per_share": 5.0},
        source="lixinger",
    ))
    db_session.add(CorpAction(
        stock_code="600519", ex_date=date(2026, 6, 15),
        action_type="stock_dividend", params_json={"per_10_shares": 5.0},
        source="lixinger",
    ))
    db_session.flush()
    count = process_pending_corp_actions(db_session)
    db_session.commit()
    assert count == 2
    # all processed
    pending = db_session.query(CorpAction).filter(CorpAction.processed_at.is_(None)).count()
    assert pending == 0


def test_process_pending_skips_already_processed(db_session, setup):
    db_session.add(CorpAction(
        stock_code="600519", ex_date=date(2026, 7, 15),
        action_type="cash_dividend", params_json={"per_share": 5.0},
        source="lixinger",
        processed_at=datetime(2026, 7, 16, 9, 0),  # already done
    ))
    db_session.flush()
    count = process_pending_corp_actions(db_session)
    assert count == 0


def test_process_pending_filters_by_ex_date(db_session, setup):
    """Optionally filter to actions whose ex_date <= today."""
    from datetime import timedelta
    db_session.add(CorpAction(
        stock_code="600519", ex_date=date.today() - timedelta(days=1),
        action_type="cash_dividend", params_json={"per_share": 5.0},
        source="lixinger",
    ))
    db_session.add(CorpAction(
        stock_code="600519", ex_date=date.today() + timedelta(days=10),
        action_type="cash_dividend", params_json={"per_share": 7.0},
        source="lixinger",
    ))
    db_session.flush()
    count = process_pending_corp_actions(db_session, as_of=date.today())
    db_session.commit()
    assert count == 1  # only the past one
