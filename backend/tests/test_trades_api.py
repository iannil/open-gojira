"""Test /api/trades endpoints."""

from datetime import date, datetime

import pytest

from app.models.broker_fee_config import BrokerFeeConfig
from app.models.cash_balance import CashBalance
from app.models.stock import Stock


@pytest.fixture
def setup(client, db_session):
    db_session.add(Stock(code="600519", name="贵州茅台", exchange="sh"))
    db_session.add(Stock(code="000001", name="平安银行", exchange="sz"))
    db_session.add(CashBalance(id=1, balance=500000.0))
    db_session.add(BrokerFeeConfig(
        broker_name="default", commission_rate=0.00025, commission_min=5.0,
        stamp_duty_rate=0.0005, transfer_fee_rate=0.00001,
        effective_from=date(2023, 10, 23), is_active=True,
    ))
    db_session.flush()


def test_create_buy_trade(client, setup):
    resp = client.post("/api/trades", json={
        "stock_code": "600519", "side": "BUY",
        "price": 1680.0, "quantity": 100,
        "filled_at": "2026-06-12T10:30:00",
        "source": "manual",
    })
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["stock_code"] == "600519"
    assert data["side"] == "BUY"
    assert data["quantity"] == 100
    assert data["commission"] == pytest.approx(42.0, abs=0.01)
    assert data["total_value"] == pytest.approx(168043.68, abs=0.01)


def test_create_sell_trade(client, setup):
    # BUY first so we have a position (also seeds cash impact)
    client.post("/api/trades", json={
        "stock_code": "600519", "side": "BUY",
        "price": 100.0, "quantity": 100,
        "filled_at": "2026-06-11T10:00:00",
    })
    resp = client.post("/api/trades", json={
        "stock_code": "600519", "side": "SELL",
        "price": 110.0, "quantity": 50,
        "filled_at": "2026-06-12T10:30:00",
    })
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["side"] == "SELL"
    assert data["quantity"] == -50  # SELL quantity negative
    # notional 5500 - commission 5 (min) - stamp 2.75 - transfer 0.055 = 5492.195
    assert data["total_value"] == pytest.approx(5492.195, abs=0.01)


def test_create_trade_insufficient_cash(client, db_session):
    db_session.add(Stock(code="600519", name="贵州茅台", exchange="sh"))
    db_session.add(CashBalance(id=1, balance=100.0))
    db_session.add(BrokerFeeConfig(
        broker_name="default", commission_rate=0.00025, commission_min=5.0,
        stamp_duty_rate=0.0005, transfer_fee_rate=0.00001,
        effective_from=date(2023, 10, 23), is_active=True,
    ))
    db_session.flush()
    resp = client.post("/api/trades", json={
        "stock_code": "600519", "side": "BUY",
        "price": 1000.0, "quantity": 100,
        "filled_at": "2026-06-12T10:30:00",
    })
    assert resp.status_code == 400
    assert "Insufficient cash" in resp.json()["detail"]


def test_create_trade_no_fee_config(client, db_session):
    """No broker_fee_config in DB → 500 from NoActiveFeeConfigError."""
    db_session.add(Stock(code="600519", name="贵州茅台", exchange="sh"))
    db_session.add(CashBalance(id=1, balance=100000.0))
    db_session.flush()
    resp = client.post("/api/trades", json={
        "stock_code": "600519", "side": "BUY",
        "price": 100.0, "quantity": 10,
        "filled_at": "2026-06-12T10:30:00",
    })
    assert resp.status_code == 500


def test_list_trades(client, setup):
    client.post("/api/trades", json={
        "stock_code": "600519", "side": "BUY",
        "price": 100.0, "quantity": 100,
        "filled_at": "2026-06-12T10:00:00",
    })
    resp = client.get("/api/trades")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["stock_code"] == "600519"


def test_filter_trades_by_code(client, setup):
    client.post("/api/trades", json={
        "stock_code": "600519", "side": "BUY",
        "price": 100.0, "quantity": 100,
        "filled_at": "2026-06-12T10:00:00",
    })
    client.post("/api/trades", json={
        "stock_code": "000001", "side": "BUY",
        "price": 10.0, "quantity": 100,
        "filled_at": "2026-06-12T11:00:00",
    })
    resp = client.get("/api/trades?code=600519")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["stock_code"] == "600519"


def test_filter_trades_by_side(client, setup):
    client.post("/api/trades", json={
        "stock_code": "600519", "side": "BUY",
        "price": 100.0, "quantity": 100,
        "filled_at": "2026-06-11T10:00:00",
    })
    client.post("/api/trades", json={
        "stock_code": "600519", "side": "SELL",
        "price": 110.0, "quantity": 50,
        "filled_at": "2026-06-12T10:00:00",
    })
    resp = client.get("/api/trades?side=SELL")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["side"] == "SELL"


def test_get_trade_by_id(client, setup):
    r = client.post("/api/trades", json={
        "stock_code": "600519", "side": "BUY",
        "price": 100.0, "quantity": 100,
        "filled_at": "2026-06-12T10:00:00",
    })
    trade_id = r.json()["id"]
    resp = client.get(f"/api/trades/{trade_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == trade_id


def test_get_trade_not_found(client, setup):
    resp = client.get("/api/trades/9999")
    assert resp.status_code == 404


def test_reverse_buy_trade(client, setup):
    # Original BUY
    r = client.post("/api/trades", json={
        "stock_code": "600519", "side": "BUY",
        "price": 100.0, "quantity": 100,
        "filled_at": "2026-06-12T10:00:00",
    })
    trade_id = r.json()["id"]
    original_total = r.json()["total_value"]

    # Reverse it
    resp = client.post(f"/api/trades/{trade_id}/reverse")
    assert resp.status_code == 201, resp.text
    reversed_trade = resp.json()
    assert reversed_trade["side"] == "SELL"
    assert reversed_trade["quantity"] == -100
    assert reversed_trade["total_value"] == pytest.approx(-original_total, abs=0.01)
    assert reversed_trade["source"] == "reversal"
    assert reversed_trade["source_ref"] == str(trade_id)
    assert reversed_trade["reversed_by_trade_id"] is None  # the new one has no reversal

    # Original trade should now have reversed_by_trade_id pointing back
    orig = client.get(f"/api/trades/{trade_id}").json()
    assert orig["reversed_by_trade_id"] == reversed_trade["id"]


def test_reverse_trade_already_reversed(client, setup):
    r = client.post("/api/trades", json={
        "stock_code": "600519", "side": "BUY",
        "price": 100.0, "quantity": 100,
        "filled_at": "2026-06-12T10:00:00",
    })
    trade_id = r.json()["id"]
    client.post(f"/api/trades/{trade_id}/reverse")
    # Try to reverse again
    resp = client.post(f"/api/trades/{trade_id}/reverse")
    assert resp.status_code == 409


def test_reverse_trade_not_found(client, setup):
    resp = client.post("/api/trades/9999/reverse")
    assert resp.status_code == 404


def test_reverse_cannot_reverse_a_reversal(client, setup):
    r = client.post("/api/trades", json={
        "stock_code": "600519", "side": "BUY",
        "price": 100.0, "quantity": 100,
        "filled_at": "2026-06-12T10:00:00",
    })
    trade_id = r.json()["id"]
    rev = client.post(f"/api/trades/{trade_id}/reverse").json()
    # Try to reverse the reversal itself
    resp = client.post(f"/api/trades/{rev['id']}/reverse")
    assert resp.status_code == 400


def test_reverse_updates_cash_balance(client, setup):
    initial = client.get("/api/cash/balance").json()["balance"]
    r = client.post("/api/trades", json={
        "stock_code": "600519", "side": "BUY",
        "price": 100.0, "quantity": 100,
        "filled_at": "2026-06-12T10:00:00",
    })
    trade_id = r.json()["id"]
    after_buy = client.get("/api/cash/balance").json()["balance"]
    assert after_buy < initial
    client.post(f"/api/trades/{trade_id}/reverse")
    after_reverse = client.get("/api/cash/balance").json()["balance"]
    # Net cash impact should be ~0 (modulo fee-direction asymmetry, but here
    # reversal exactly mirrors the original total_value)
    assert after_reverse == pytest.approx(initial, abs=0.01)


def test_commission_override_via_api(client, setup):
    resp = client.post("/api/trades", json={
        "stock_code": "600519", "side": "BUY",
        "price": 1680.0, "quantity": 100,
        "filled_at": "2026-06-12T10:30:00",
        "commission_override": 50.0,
    })
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["commission"] == 50.0
    assert data["fee_source"] == "manual_override"
