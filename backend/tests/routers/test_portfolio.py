"""Router tests for the read-only portfolio endpoints (Q2-A).

Positions are derived from the Trade ledger; entry/exit is via trades, so the
old create/update/delete/sell endpoints are gone. These tests seed Trade rows
and exercise the surviving read views (list / summary / available).
"""

from datetime import datetime
from unittest.mock import patch

from app.models.stock import Stock
from app.models.trade import Trade
from tests.conftest import TestSessionLocal


def _seed_stock(code="600519", name="贵州茅台", industry="白酒", tier="core", prev_close=100.0):
    with TestSessionLocal() as db:
        db.add(Stock(code=code, name=name, industry=industry, tier=tier, prev_close=prev_close))
        db.commit()


def _seed_buy(code="600519", quantity=100, price=100.0, when=datetime(2026, 1, 15, 10, 0)):
    with TestSessionLocal() as db:
        db.add(Trade(stock_code=code, side="BUY", price=price, quantity=quantity,
                     filled_at=when, total_value=price * quantity, source="manual"))
        db.commit()


class TestListHoldings:
    """GET /api/portfolio"""

    def test_list_empty(self, client):
        resp = client.get("/api/portfolio")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_returns_open_position(self, client):
        _seed_stock()
        _seed_buy()
        with patch("app.services.holding_service._get_cached_price", return_value=None):
            resp = client.get("/api/portfolio")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["stock_code"] == "600519"
        assert data[0]["quantity"] == 100
        assert data[0]["buy_price"] == 100.0

    def test_fully_sold_position_excluded(self, client):
        _seed_stock()
        _seed_buy(quantity=100)
        with TestSessionLocal() as db:
            db.add(Trade(stock_code="600519", side="SELL", price=110.0, quantity=-100,
                         filled_at=datetime(2026, 3, 1, 10, 0), total_value=11000.0,
                         source="manual"))
            db.commit()
        with patch("app.services.holding_service._get_cached_price", return_value=None):
            resp = client.get("/api/portfolio")
        assert resp.json() == []


class TestPortfolioSummary:
    """GET /api/portfolio/summary"""

    def test_summary_empty(self, client):
        resp = client.get("/api/portfolio/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_cost"] == 0.0
        assert data["total_value"] == 0.0
        assert data["position_count"] == 0
        assert data["holdings"] == []

    def test_summary_with_position(self, client):
        _seed_stock()
        _seed_buy(quantity=100, price=100.0)  # cost 10000
        with patch("app.services.holding_service._get_cached_price", return_value=120.0):
            resp = client.get("/api/portfolio/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["position_count"] == 1
        assert data["total_cost"] == 10000.0
        assert data["total_value"] == 12000.0
        assert data["total_pnl"] == 2000.0
        assert abs(data["total_pnl_pct"] - 20.0) < 0.01
        assert len(data["holdings"]) == 1


class TestAvailableQuantity:
    """GET /api/portfolio/{code}/available — T+1 derived from the trade ledger."""

    def test_settled_buy_fully_available(self, client):
        _seed_stock()
        _seed_buy(quantity=100, when=datetime(2020, 1, 2, 10, 0))  # long settled
        resp = client.get("/api/portfolio/600519/available")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 100
        assert data["available"] == 100
        assert data["frozen"] == 0

    def test_unknown_stock_404(self, client):
        resp = client.get("/api/portfolio/999999/available")
        assert resp.status_code == 404
