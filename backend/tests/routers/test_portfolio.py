"""Router tests for portfolio (holdings) endpoints."""

from datetime import date

from app.models.holding import Holding
from app.models.stock import Stock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_STOCK_A = {
    "code": "600519",
    "name": "贵州茅台",
    "industry": "白酒",
    "tier": "core",
}

_STOCK_B = {
    "code": "000858",
    "name": "五粮液",
    "industry": "白酒",
    "tier": "satellite",
}


def _seed_stock(client, stock_data: dict) -> None:
    """Insert a Stock row directly via the test DB session."""
    # We use the app dependency override — get the session from the test
    # session factory to avoid hitting the real DB.
    from tests.conftest import TestSessionLocal

    with TestSessionLocal() as db:
        db.add(Stock(**stock_data))
        db.commit()


def _seed_stock_and_holding(client, stock_data=_STOCK_A) -> dict:
    """Seed a stock, create a holding via API, and return the holding JSON."""
    _seed_stock(client, stock_data)
    payload = {
        "stock_code": stock_data["code"],
        "buy_date": "2026-01-15",
        "buy_price": 100.0,
        "quantity": 100,
        "stop_profit_price": 120.0,
        "trade_rationale": "Test buy",
    }
    resp = client.post("/api/portfolio", json=payload)
    assert resp.status_code == 201, f"Setup create failed: {resp.text}"
    return resp.json()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCreateHolding:
    """POST /api/portfolio"""

    def test_create_holding_returns_201(self, client):
        holding = _seed_stock_and_holding(client)
        assert holding["id"] is not None
        assert holding["stock_code"] == "600519"
        assert holding["stock_name"] == "贵州茅台"
        assert holding["stock_industry"] == "白酒"
        assert holding["buy_price"] == 100.0
        assert holding["quantity"] == 100
        assert holding["stop_profit_price"] == 120.0
        assert holding["sell_date"] is None
        assert holding["sell_price"] is None

    def test_create_holding_nonexistent_stock_returns_404(self, client):
        payload = {
            "stock_code": "999999",
            "buy_date": "2026-01-15",
            "buy_price": 10.0,
            "quantity": 50,
            "stop_profit_price": 12.0,
        }
        resp = client.post("/api/portfolio", json=payload)
        assert resp.status_code == 404
        assert "999999" in resp.json()["detail"]


class TestListHoldings:
    """GET /api/portfolio"""

    def test_list_holdings_empty(self, client):
        resp = client.get("/api/portfolio")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_holdings_returns_created(self, client):
        _seed_stock_and_holding(client)
        resp = client.get("/api/portfolio")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["stock_code"] == "600519"

    def test_list_holdings_active_only_excludes_sold(self, client):
        holding = _seed_stock_and_holding(client)
        sell_payload = {
            "sell_date": "2026-03-01",
            "sell_price": 110.0,
            "sell_thesis": "Take profit",
        }
        resp = client.post(
            f"/api/portfolio/{holding['id']}/sell", json=sell_payload
        )
        assert resp.status_code == 200

        resp = client.get("/api/portfolio", params={"active_only": True})
        assert resp.status_code == 200
        assert resp.json() == []

        # Without active_only, the sold holding is still listed
        resp_all = client.get("/api/portfolio", params={"active_only": False})
        assert resp_all.status_code == 200
        assert len(resp_all.json()) == 1


class TestGetHolding:
    """GET /api/portfolio/{holding_id}"""

    def test_get_holding_by_id(self, client):
        holding = _seed_stock_and_holding(client)
        resp = client.get(f"/api/portfolio/{holding['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == holding["id"]
        assert data["stock_code"] == "600519"
        assert data["stock_name"] == "贵州茅台"

    def test_get_nonexistent_holding_returns_404(self, client):
        resp = client.get("/api/portfolio/99999")
        assert resp.status_code == 404
        assert "99999" in resp.json()["detail"]


class TestUpdateHolding:
    """PUT /api/portfolio/{holding_id}"""

    def test_update_holding_fields(self, client):
        holding = _seed_stock_and_holding(client)
        update_payload = {
            "buy_price": 105.0,
            "quantity": 200,
            "stop_profit_price": 130.0,
        }
        resp = client.put(
            f"/api/portfolio/{holding['id']}", json=update_payload
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["buy_price"] == 105.0
        assert data["quantity"] == 200
        assert data["stop_profit_price"] == 130.0

    def test_update_partial_only_sends_changed_fields(self, client):
        holding = _seed_stock_and_holding(client)
        resp = client.put(
            f"/api/portfolio/{holding['id']}", json={"quantity": 150}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["quantity"] == 150
        # Other fields unchanged
        assert data["buy_price"] == 100.0
        assert data["stop_profit_price"] == 120.0

    def test_update_nonexistent_holding_returns_404(self, client):
        resp = client.put("/api/portfolio/99999", json={"quantity": 10})
        assert resp.status_code == 404


class TestDeleteHolding:
    """DELETE /api/portfolio/{holding_id}"""

    def test_delete_holding(self, client):
        holding = _seed_stock_and_holding(client)
        resp = client.delete(f"/api/portfolio/{holding['id']}")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # Verify it is gone
        resp_get = client.get(f"/api/portfolio/{holding['id']}")
        assert resp_get.status_code == 404

    def test_delete_nonexistent_holding_returns_404(self, client):
        resp = client.delete("/api/portfolio/99999")
        assert resp.status_code == 404


class TestSellHolding:
    """POST /api/portfolio/{holding_id}/sell"""

    def test_sell_holding(self, client):
        holding = _seed_stock_and_holding(client)
        sell_payload = {
            "sell_date": "2026-06-01",
            "sell_price": 115.0,
            "sell_thesis": "Target reached",
        }
        resp = client.post(
            f"/api/portfolio/{holding['id']}/sell", json=sell_payload
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["sell_date"] == "2026-06-01"
        assert data["sell_price"] == 115.0
        assert data["sell_thesis"] == "Target reached"

    def test_sell_nonexistent_holding_returns_404(self, client):
        sell_payload = {
            "sell_date": "2026-06-01",
            "sell_price": 50.0,
        }
        resp = client.post("/api/portfolio/99999/sell", json=sell_payload)
        assert resp.status_code == 404


class TestPortfolioSummary:
    """GET /api/portfolio/summary"""

    def test_summary_empty_portfolio(self, client):
        resp = client.get("/api/portfolio/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_cost"] == 0.0
        assert data["total_value"] == 0.0
        assert data["position_count"] == 0
        assert data["holdings"] == []

    def test_summary_with_holdings(self, client):
        _seed_stock_and_holding(client)
        resp = client.get("/api/portfolio/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["position_count"] == 1
        assert data["total_cost"] == 10000.0  # 100 * 100
        # total_value may differ from cost when a live price is available;
        # only assert it is a positive number and consistent with pnl fields.
        assert data["total_value"] > 0
        assert data["total_pnl"] == data["total_value"] - data["total_cost"]
        if data["total_cost"] > 0:
            expected_pct = (data["total_pnl"] / data["total_cost"]) * 100
            assert abs(data["total_pnl_pct"] - expected_pct) < 0.01
        assert len(data["holdings"]) == 1
        assert "warnings" in data
        assert isinstance(data["warnings"], list)
