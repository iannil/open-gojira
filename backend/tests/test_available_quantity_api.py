"""Test GET /api/portfolio/{code}/available endpoint.

v2 (trading-philosophy 决策 2026-06-25): the v1 trade-based T+1 model
(settled / frozen computed from trades) was replaced by a simple Holding read —
``available == total == Holding.quantity``, ``frozen`` always 0 (no freeze
concept). Positions come from Holding (CSV import), not from BUY trades.
"""
from datetime import date

import pytest

from app.models.broker_fee_config import BrokerFeeConfig
from app.models.cash_balance import CashBalance
from app.models.holding import Holding
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


def _add_holding(db, code, quantity, sell_date=None):
    db.add(Holding(
        stock_code=code, buy_date=date(2026, 6, 11), buy_price=100.0,
        quantity=quantity, stop_profit_price=130.0, sell_date=sell_date,
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


def test_available_from_holding(client, setup, db_session):
    """Holding qty → available = total = qty, frozen = 0 (no T+1 freeze in v2)."""
    _add_holding(db_session, "600519", 200)
    resp = client.get("/api/portfolio/600519/available")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] == 200
    assert data["frozen"] == 0
    assert data["total"] == 200


def test_available_excludes_sold_holding(client, setup, db_session):
    """A holding with sell_date set is closed → not counted as available."""
    _add_holding(db_session, "600519", 200, sell_date=date(2026, 6, 12))
    resp = client.get("/api/portfolio/600519/available")
    assert resp.status_code == 200
    assert resp.json()["available"] == 0


def test_available_stock_not_found(client, setup):
    resp = client.get("/api/portfolio/999999/available")
    assert resp.status_code == 404


def test_available_other_stock_unaffected(client, setup, db_session):
    """A holding on 600519 must not affect 000001's available."""
    _add_holding(db_session, "600519", 500)
    resp = client.get("/api/portfolio/000001/available")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] == 0
    assert data["total"] == 0
