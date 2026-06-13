"""Test POST /api/drafts/{id}/execute — merge execute + trade entry.

重审决策 #2 (2026-06-13): 点击执行 → 同时记录 trade,避免用户在
两个独立步骤里重复输入同一笔成交。
"""

from datetime import date, datetime

import pytest

from app.models.broker_fee_config import BrokerFeeConfig
from app.models.cash_balance import CashBalance
from app.models.draft import Draft
from app.models.plan import Plan
from app.models.stock import Stock
from app.models.trade import Trade


@pytest.fixture
def seed(db_session):
    """Seed stock + cash + fee_config + plan + pending BUY draft."""
    db_session.add(Stock(
        code="600519", name="贵州茅台", exchange="sh",
        listing_status="normally_listed", prev_close=100.0,
    ))
    db_session.add(CashBalance(id=1, balance=1_000_000.0))
    db_session.add(BrokerFeeConfig(
        broker_name="default", commission_rate=0.00025, commission_min=5.0,
        stamp_duty_rate=0.0005, transfer_fee_rate=0.00001,
        effective_from=date(2023, 10, 23), is_active=True,
    ))
    db_session.add(Plan(
        name="t", slug="t", description="", status="active",
        strategy_composition_json='{"strategy_ids":[],"logic":"AND"}',
        scan_scope_json='{"type":"custom","values":[]}',
        schedule_cron="0 0 * * *", is_builtin=False,
    ))
    db_session.flush()
    db_session.add(Draft(
        plan_id=1, code="600519", side="BUY", status="pending",
        step_kind="buy_ladder", step_index=0,
        add_pct=0.10, reason="test",
        triggered_at=datetime(2026, 6, 13, 18, 0),
    ))
    db_session.flush()


def test_execute_buy_draft_records_trade(client, db_session, seed):
    """重审 #2: BUY draft 执行时,buy_price+quantity → 自动记录 Trade。"""
    resp = client.post("/api/drafts/1/execute", json={
        "buy_price": 100.0,
        "quantity": 200,
        "discipline_checklist": {"no_borrow": True, "not_emotion": True},
    })
    assert resp.status_code == 200, resp.text

    trades = db_session.query(Trade).filter_by(stock_code="600519").all()
    assert len(trades) == 1, "执行 BUY draft 应记录 1 笔 trade"
    t = trades[0]
    assert t.side == "BUY"
    assert t.price == 100.0
    assert t.quantity == 200
    assert t.source == "draft"
    assert t.source_ref == "1", "source_ref 应为 draft id"


def test_execute_draft_status_becomes_executed(client, db_session, seed):
    """执行后 draft.status → executed。"""
    client.post("/api/drafts/1/execute", json={
        "buy_price": 100.0, "quantity": 100,
    })
    db_session.expire_all()
    d = db_session.get(Draft, 1)
    assert d.status == "executed"
    assert d.executed_at is not None


def test_execute_without_price_qty_still_marks_executed(client, db_session, seed):
    """无 broker 回报时,仍允许仅标记 executed (向后兼容,跳过 trade 录入)。"""
    resp = client.post("/api/drafts/1/execute", json={})
    assert resp.status_code == 200, resp.text
    db_session.expire_all()
    d = db_session.get(Draft, 1)
    assert d.status == "executed"
    # No trade recorded
    trades = db_session.query(Trade).filter_by(stock_code="600519").all()
    assert len(trades) == 0


def test_execute_buy_draft_decreases_cash(client, db_session, seed):
    """执行 BUY draft 时,cash_balance 应同步减少 (trade_service 原子更新)。"""
    client.post("/api/drafts/1/execute", json={
        "buy_price": 100.0, "quantity": 100,
    })
    db_session.expire_all()
    cb = db_session.get(CashBalance, 1)
    # BUY 100 @ 100 = 10000 notional + ~2.5 commission + 0.1 transfer = ~10002.6
    assert cb.balance < 1_000_000.0
    assert cb.balance > 1_000_000.0 - 10100.0
