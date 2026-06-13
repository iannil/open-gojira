"""Test GET /api/portfolio/{code}/available endpoint."""
from datetime import date, datetime, timedelta

import pytest

from app.models.broker_fee_config import BrokerFeeConfig
from app.models.cash_balance import CashBalance
from app.models.stock import Stock


@pytest.fixture
def setup(client, db_session):
    db_session.add(Stock(
        code="600519", name="贵州茅台", exchange="sh",
        listing_status="normally_listed", prev_close=100.0,
    ))
    db_session.add(Stock(
        code="000001", name="平安银行", exchange="sz",
        listing_status="normally_listed", prev_close=10.0,
    ))
    db_session.add(CashBalance(id=1, balance=1_000_000.0))
    db_session.add(BrokerFeeConfig(
        broker_name="default", commission_rate=0.00025, commission_min=5.0,
        stamp_duty_rate=0.0005, transfer_fee_rate=0.00001,
        effective_from=date(2023, 10, 23), is_active=True,
    ))
    db_session.flush()


def _yesterday_trade(client, code, side, price, qty, days_ago=1):
    """Record a trade N days before today (settled, no longer frozen)."""
    filled = datetime.now() - timedelta(days=days_ago)
    resp = client.post("/api/trades", json={
        "stock_code": code,
        "side": side,
        "price": price,
        "quantity": qty,
        "filled_at": filled.isoformat(),
        "source": "manual",
    })
    assert resp.status_code == 201, resp.text


def _today_trade(client, code, side, price, qty):
    """Record a trade happening today."""
    resp = client.post("/api/trades", json={
        "stock_code": code,
        "side": side,
        "price": price,
        "quantity": qty,
        "filled_at": datetime.now().isoformat(),
        "source": "manual",
    })
    assert resp.status_code == 201, resp.text


def test_available_no_position(client, setup):
    """No trades at all → all zeros."""
    resp = client.get("/api/portfolio/600519/available")
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == "600519"
    assert data["available"] == 0
    assert data["frozen"] == 0
    assert data["total"] == 0


def test_available_only_settled_buy(client, setup):
    """Yesterday's BUY: available = total = qty, frozen = 0."""
    _yesterday_trade(client, "600519", "BUY", 100.0, 200, days_ago=1)
    resp = client.get("/api/portfolio/600519/available")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] == 200
    assert data["frozen"] == 0
    assert data["total"] == 200


def test_available_today_buy_frozen(client, setup):
    """Today's BUY is frozen, not available."""
    _today_trade(client, "600519", "BUY", 100.0, 100)
    resp = client.get("/api/portfolio/600519/available")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] == 0
    assert data["frozen"] == 100
    assert data["total"] == 100


def test_available_mixed_settled_and_today(client, setup):
    """Yesterday's BUY 300 + today's BUY 100 → available 300, frozen 100."""
    _yesterday_trade(client, "600519", "BUY", 100.0, 300, days_ago=1)
    _today_trade(client, "600519", "BUY", 105.0, 100)
    resp = client.get("/api/portfolio/600519/available")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] == 300
    assert data["frozen"] == 100
    assert data["total"] == 400


def test_available_after_partial_sell(client, setup):
    """Settled BUY 200 - SELL 80 → available 120."""
    _yesterday_trade(client, "600519", "BUY", 100.0, 200, days_ago=2)
    _yesterday_trade(client, "600519", "SELL", 110.0, 80, days_ago=1)
    resp = client.get("/api/portfolio/600519/available")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] == 120
    assert data["total"] == 120


def test_available_stock_not_found(client, setup):
    resp = client.get("/api/portfolio/999999/available")
    assert resp.status_code == 404


def test_available_other_stock_unaffected(client, setup):
    """BUY on 600519 should not affect available of 000001."""
    _yesterday_trade(client, "600519", "BUY", 100.0, 500, days_ago=1)
    resp = client.get("/api/portfolio/000001/available")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] == 0
    assert data["total"] == 0
