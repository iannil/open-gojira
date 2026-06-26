"""Test GET /api/portfolio/{code}/available endpoint.

Q2-A (2026-06-26): availability is derived from the Trade ledger with T+1
freeze — a settled (prior-day) BUY is fully available; same-day buys are frozen.
"""
from datetime import date, datetime

import pytest

from app.models.broker_fee_config import BrokerFeeConfig
from app.models.cash_balance import CashBalance
from app.models.trade import Trade
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


def _settled_buy(db, code, quantity):
    """Prior-day BUY → fully T+1-available."""
    db.add(Trade(
        stock_code=code, side="BUY", price=100.0, quantity=quantity,
        filled_at=datetime(2020, 1, 2, 10, 0), total_value=100.0 * quantity,
        source="manual",
    ))
    db.flush()


def test_available_no_position(client, setup):
    """No holding → all zeros."""
    resp = client.get("/api/portfolio/600519/available")
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == "600519"
    assert data["available"] == 0
    assert data["frozen"] == 0
    assert data["total"] == 0


def test_available_from_settled_buy(client, setup, db_session):
    """Settled BUY qty → available = total = qty, frozen = 0."""
    _settled_buy(db_session, "600519", 200)
    resp = client.get("/api/portfolio/600519/available")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] == 200
    assert data["frozen"] == 0
    assert data["total"] == 200


def test_available_excludes_sold_position(client, setup, db_session):
    """A fully-sold position is closed → not counted as available."""
    _settled_buy(db_session, "600519", 200)
    db_session.add(Trade(
        stock_code="600519", side="SELL", price=101.0, quantity=-200,
        filled_at=datetime(2020, 1, 3, 10, 0), total_value=101.0 * 200, source="manual",
    ))
    db_session.flush()
    resp = client.get("/api/portfolio/600519/available")
    assert resp.status_code == 200
    assert resp.json()["available"] == 0


def test_available_stock_not_found(client, setup):
    resp = client.get("/api/portfolio/999999/available")
    assert resp.status_code == 404


def test_available_other_stock_unaffected(client, setup, db_session):
    """A position on 600519 must not affect 000001's available."""
    _settled_buy(db_session, "600519", 500)
    resp = client.get("/api/portfolio/000001/available")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] == 0
    assert data["total"] == 0
