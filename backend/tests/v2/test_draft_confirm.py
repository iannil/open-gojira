"""Draft confirm/execute flow (P0-2, paper-trading loop).

Confirming a draft records the *actual* fill as a Trade (source=manual,
source_ref=draft.id) and flips the draft to executed. The position then derives
from that Trade (Q2-A). Actual price/quantity may freely deviate from the
draft's suggested values — the difference is the slippage we want to observe.
"""
from datetime import date, datetime

import pytest

from app.models.broker_fee_config import BrokerFeeConfig
from app.models.cash_balance import CashBalance
from app.models.draft import Draft
from app.models.stock import Stock
from app.models.trade import Trade
from tests.conftest import TestSessionLocal


@pytest.fixture
def setup():
    with TestSessionLocal() as db:
        db.add(Stock(code="600519", name="贵州茅台", exchange="sh",
                     listing_status="normally_listed", prev_close=100.0))
        db.add(CashBalance(id=1, balance=1_000_000.0))
        db.add(BrokerFeeConfig(
            broker_name="default", commission_rate=0.00025, commission_min=5.0,
            stamp_duty_rate=0.0005, transfer_fee_rate=0.00001,
            effective_from=date(2023, 10, 23), is_active=True,
        ))
        db.commit()


def _pending_buy_draft(target_price=98.0, suggested_quantity=100) -> int:
    with TestSessionLocal() as db:
        d = Draft(code="600519", side="BUY", status="pending",
                  step_kind="aggressive", step_index=0, reason="价格入区间",
                  target_price=target_price, suggested_quantity=suggested_quantity)
        db.add(d)
        db.commit()
        return d.id


def test_confirm_buy_records_manual_trade_and_marks_executed(client, setup):
    draft_id = _pending_buy_draft()
    resp = client.post(f"/api/drafts/{draft_id}/execute", json={
        "price": 101.0, "quantity": 100, "filled_at": "2026-06-12T10:00:00",
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "executed"

    with TestSessionLocal() as db:
        trade = db.query(Trade).filter(Trade.source_ref == str(draft_id)).one()
        assert trade.source == "manual"
        assert trade.side == "BUY"
        assert trade.price == 101.0
        assert trade.quantity == 100


def test_actual_may_deviate_from_suggested(client, setup):
    """Actual price/quantity are recorded as-is even if they differ from the
    draft's suggested values, and the position derives from the actual fill."""
    draft_id = _pending_buy_draft(target_price=98.0, suggested_quantity=100)
    resp = client.post(f"/api/drafts/{draft_id}/execute", json={
        "price": 95.0, "quantity": 60, "filled_at": "2026-06-12T10:00:00",
    })
    assert resp.status_code == 200, resp.text
    from app.services import position_service
    with TestSessionLocal() as db:
        pos = position_service.position_for(db, "600519", price_lookup=lambda _c: None)
        assert pos.quantity == 60                          # actual, not suggested 100
        assert pos.avg_cost == pytest.approx(95.0, abs=0.5)  # actual≈95 (+fees), not target 98


def test_confirm_sell_draft_records_sell(client, setup):
    """Confirming a SELL draft records a SELL trade against an existing position."""
    # Seed a settled BUY position (prior day → T+1 available).
    with TestSessionLocal() as db:
        db.add(Trade(stock_code="600519", side="BUY", price=100.0, quantity=100,
                     filled_at=datetime(2026, 6, 11, 10, 0), total_value=10000.0,
                     source="manual"))
        d = Draft(code="600519", side="SELL", status="pending",
                  step_kind="reduce", step_index=0, reason="论点失效清仓")
        db.add(d)
        db.commit()
        draft_id = d.id
    resp = client.post(f"/api/drafts/{draft_id}/execute", json={
        "price": 110.0, "quantity": 100, "filled_at": "2026-06-12T14:00:00",
    })
    assert resp.status_code == 200, resp.text
    with TestSessionLocal() as db:
        trade = db.query(Trade).filter(Trade.source_ref == str(draft_id)).one()
        assert trade.side == "SELL"
        assert trade.quantity == -100


def test_confirm_without_fill_data_marks_executed_no_trade(client, setup):
    draft_id = _pending_buy_draft()
    resp = client.post(f"/api/drafts/{draft_id}/execute", json={})
    assert resp.status_code == 200
    assert resp.json()["status"] == "executed"
    with TestSessionLocal() as db:
        assert db.query(Trade).filter(Trade.source_ref == str(draft_id)).count() == 0


def test_confirm_already_executed_returns_409(client, setup):
    draft_id = _pending_buy_draft()
    first = client.post(f"/api/drafts/{draft_id}/execute", json={
        "price": 100.0, "quantity": 100, "filled_at": "2026-06-12T10:00:00",
    })
    assert first.status_code == 200
    again = client.post(f"/api/drafts/{draft_id}/execute", json={
        "price": 100.0, "quantity": 100, "filled_at": "2026-06-12T10:00:00",
    })
    assert again.status_code == 409
