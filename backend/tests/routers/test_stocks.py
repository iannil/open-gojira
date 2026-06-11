"""Tests for the stocks router endpoints."""

from unittest.mock import patch


class TestListStocks:
    """GET /api/stocks"""

    def test_empty_list(self, client):
        resp = client.get("/api/stocks")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_returns_created_stocks(self, client):
        client.post("/api/stocks", json={"code": "600519", "name": "贵州茅台", "auto_fetch": False})
        client.post("/api/stocks", json={"code": "000858", "name": "五粮液", "auto_fetch": False})

        resp = client.get("/api/stocks")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        codes = {s["code"] for s in data}
        assert codes == {"600519", "000858"}


class TestCreateStock:
    """POST /api/stocks"""

    def test_create_stock_without_auto_fetch(self, client):
        resp = client.post(
            "/api/stocks",
            json={"code": "600519", "name": "贵州茅台", "auto_fetch": False},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["code"] == "600519"
        assert data["name"] == "贵州茅台"
        assert data["qiu_score"] == 0

    def test_create_stock_code_only(self, client):
        resp = client.post(
            "/api/stocks",
            json={"code": "600519", "auto_fetch": False},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["code"] == "600519"
        # name falls back to code when not provided
        assert data["name"] == "600519"

    def test_create_duplicate_stock_returns_409(self, client):
        client.post("/api/stocks", json={"code": "600519", "auto_fetch": False})

        resp = client.post(
            "/api/stocks",
            json={"code": "600519", "name": "贵州茅台", "auto_fetch": False},
        )
        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"]

    @patch("app.routers.stocks.fetch_stock_info")
    def test_create_stock_with_auto_fetch(self, mock_fetch, client):
        mock_fetch.return_value = {"code": "600519", "name": "贵州茅台", "industry": "白酒"}

        resp = client.post(
            "/api/stocks",
            json={"code": "600519", "auto_fetch": True},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "贵州茅台"
        assert data["industry"] == "白酒"
        mock_fetch.assert_called_once_with("600519")

    @patch("app.routers.stocks.fetch_stock_info")
    def test_create_stock_auto_fetch_returns_none(self, mock_fetch, client):
        mock_fetch.return_value = None

        resp = client.post(
            "/api/stocks",
            json={"code": "600519", "auto_fetch": True},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["code"] == "600519"
        # name falls back to code when fetch returns None and no name given
        assert data["name"] == "600519"


class TestGetStock:
    """GET /api/stocks/{code}"""

    def test_get_existing_stock(self, client):
        client.post("/api/stocks", json={"code": "600519", "name": "贵州茅台", "auto_fetch": False})

        resp = client.get("/api/stocks/600519")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == "600519"
        assert data["name"] == "贵州茅台"

    def test_get_nonexistent_stock_returns_404(self, client):
        resp = client.get("/api/stocks/999999")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]


class TestUpdateStock:
    """PUT /api/stocks/{code}"""

    def _create_stock(self, client):
        client.post(
            "/api/stocks",
            json={"code": "600519", "name": "贵州茅台", "auto_fetch": False},
        )

    def test_update_stock_fields(self, client):
        self._create_stock(client)

        resp = client.put(
            "/api/stocks/600519",
            json={"industry": "白酒", "tier": "core", "security_theme": "消费"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["industry"] == "白酒"
        assert data["tier"] == "core"
        assert data["security_theme"] == "消费"
        # unchanged fields remain
        assert data["name"] == "贵州茅台"
        assert data["code"] == "600519"

    def test_update_stock_qiu_score(self, client):
        self._create_stock(client)

        resp = client.put("/api/stocks/600519", json={"qiu_score": 2})
        assert resp.status_code == 200
        assert resp.json()["qiu_score"] == 2

    def test_update_stock_notes(self, client):
        self._create_stock(client)

        resp = client.put("/api/stocks/600519", json={"notes": "test notes"})
        assert resp.status_code == 200
        assert resp.json()["notes"] == "test notes"

    def test_update_nonexistent_stock_returns_404(self, client):
        resp = client.put("/api/stocks/999999", json={"name": "nope"})
        assert resp.status_code == 404

    def test_update_stock_with_empty_body(self, client):
        self._create_stock(client)

        resp = client.put("/api/stocks/600519", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "贵州茅台"
        assert data["code"] == "600519"


class TestUpdateThesisVariables:
    """PUT /api/stocks/{code}/thesis-variables"""

    def test_update_thesis_variables(self, client):
        client.post("/api/stocks", json={"code": "600519", "name": "贵州茅台", "auto_fetch": False})

        variables = [
            {"name": "茅台酒批价", "current_value": 2800, "target_condition": "> 2000", "unit": "元"},
            {"name": "基酒产量", "current_value": 5.6, "target_condition": "> 4", "unit": "万吨"},
        ]
        resp = client.put("/api/stocks/600519/thesis-variables", json=variables)
        assert resp.status_code == 200
        data = resp.json()
        assert data["thesis_variables"] is not None
        assert len(data["thesis_variables"]) == 2
        assert data["thesis_variables"][0]["name"] == "茅台酒批价"

    def test_update_thesis_variables_nonexistent_stock(self, client):
        resp = client.put(
            "/api/stocks/999999/thesis-variables",
            json=[{"name": "test"}],
        )
        assert resp.status_code == 404


class TestUpdateQiuScore:
    """PUT /api/stocks/{code}/qiu-score"""

    def test_update_qiu_score(self, client):
        client.post("/api/stocks", json={"code": "600519", "name": "贵州茅台", "auto_fetch": False})

        resp = client.put(
            "/api/stocks/600519/qiu-score",
            json={"upstream_power": 1, "downstream_power": 1, "government_power": 0, "evidence": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["qiu_score"] == 2

    def test_update_qiu_score_max(self, client):
        client.post("/api/stocks", json={"code": "600519", "name": "贵州茅台", "auto_fetch": False})

        resp = client.put(
            "/api/stocks/600519/qiu-score",
            json={"upstream_power": 1, "downstream_power": 1, "government_power": 1},
        )
        assert resp.status_code == 200
        assert resp.json()["qiu_score"] == 3

    def test_update_qiu_score_nonexistent_stock(self, client):
        resp = client.put(
            "/api/stocks/999999/qiu-score",
            json={"upstream_power": 1, "downstream_power": 1, "government_power": 1},
        )
        assert resp.status_code == 404

    def test_update_qiu_score_invalid_value(self, client):
        client.post("/api/stocks", json={"code": "600519", "name": "贵州茅台", "auto_fetch": False})

        resp = client.put(
            "/api/stocks/600519/qiu-score",
            json={"upstream_power": 2, "downstream_power": 0, "government_power": 0},
        )
        assert resp.status_code == 422


class TestUniverse:
    """GET /api/stocks/universe"""

    def test_empty_universe(self, client):
        resp = client.get("/api/stocks/universe")
        assert resp.status_code == 200
        assert resp.json() == []


class TestKlineSummary:
    """GET /api/stocks/kline-summary"""

    def test_empty_when_no_stocks(self, client):
        resp = client.get("/api/stocks/kline-summary")
        assert resp.status_code == 200
        assert resp.json() == {"items": []}

    def test_empty_when_stocks_but_no_klines(self, client):
        client.post("/api/stocks", json={"code": "600519", "name": "贵州茅台", "auto_fetch": False})

        resp = client.get("/api/stocks/kline-summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        items = data["items"]
        assert len(items) == 1
        assert items[0]["stock_code"] == "600519"
        assert items[0]["total_bars"] == 0
        assert items[0]["latest_date"] is None


class TestKlineEndpoint:
    """GET /api/stocks/{code}/kline"""

    def test_kline_stock_not_found(self, client):
        resp = client.get("/api/stocks/999999/kline")
        assert resp.status_code == 404

    @patch("app.routers.stocks.get_klines")
    def test_kline_returns_data(self, mock_klines, client):
        client.post("/api/stocks", json={"code": "600519", "name": "贵州茅台", "auto_fetch": False})

        from datetime import date
        from types import SimpleNamespace

        mock_klines.return_value = [
            SimpleNamespace(date=date(2026, 1, 1), open=100.0, high=105.0, low=98.0, close=103.0, volume=10000),
            SimpleNamespace(date=date(2026, 1, 2), open=103.0, high=108.0, low=102.0, close=107.0, volume=12000),
        ]

        resp = client.get("/api/stocks/600519/kline?days=30")
        assert resp.status_code == 200
        data = resp.json()
        assert data["stock_code"] == "600519"
        assert len(data["points"]) == 2
        assert data["points"][0]["date"] == "2026-01-01"


class TestValuationBandsEndpoint:
    """GET /api/stocks/{code}/valuation-bands"""

    def test_valuation_bands_stock_not_found(self, client):
        resp = client.get("/api/stocks/999999/valuation-bands")
        assert resp.status_code == 404

    @patch("app.routers.stocks.get_valuation_bands")
    def test_valuation_bands_returns_data(self, mock_bands, client):
        client.post("/api/stocks", json={"code": "600519", "name": "贵州茅台", "auto_fetch": False})

        mock_bands.return_value = {
            "stock_code": "600519",
            "metric": "pe_ttm",
            "dates": ["2026-01-01"],
            "close": [1800.0],
            "actual_multiple": [30.0],
            "band_levels": [{"label": "p50", "multiple": 25.0}],
            "implied_close": {"p50": [1500.0]},
        }

        resp = client.get("/api/stocks/600519/valuation-bands?metric=pe_ttm&years=5")
        assert resp.status_code == 200
        assert resp.json()["stock_code"] == "600519"
        mock_bands.assert_called_once()

    @patch("app.routers.stocks.get_valuation_bands")
    def test_valuation_bands_value_error(self, mock_bands, client):
        client.post("/api/stocks", json={"code": "600519", "name": "贵州茅台", "auto_fetch": False})

        mock_bands.side_effect = ValueError("not enough data")

        resp = client.get("/api/stocks/600519/valuation-bands")
        assert resp.status_code == 400
        assert "not enough data" in resp.json()["detail"]


class TestExternalServiceEndpoints:
    """Endpoints that delegate to external services — stock must exist in DB."""

    def _create_stock(self, client):
        client.post("/api/stocks", json={"code": "600519", "name": "贵州茅台", "auto_fetch": False})

    @patch("app.routers.stocks.get_majority_shareholders")
    def test_shareholders(self, mock_fn, client):
        self._create_stock(client)
        mock_fn.return_value = [{"holder_name": "test", "holding_ratio": 0.1}]

        resp = client.get("/api/stocks/600519/shareholders")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_shareholders_stock_not_found(self, client):
        resp = client.get("/api/stocks/999999/shareholders")
        assert resp.status_code == 404

    @patch("app.routers.stocks.get_north_flow")
    def test_north_flow(self, mock_fn, client):
        self._create_stock(client)
        mock_fn.return_value = [{"date": "2026-01-01", "net_buy_amount": 100.0}]

        resp = client.get("/api/stocks/600519/north-flow")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_north_flow_stock_not_found(self, client):
        resp = client.get("/api/stocks/999999/north-flow")
        assert resp.status_code == 404

    @patch("app.routers.stocks.get_margin_trading")
    def test_margin_trading(self, mock_fn, client):
        self._create_stock(client)
        mock_fn.return_value = [{"date": "2026-01-01", "financing_balance": 500.0}]

        resp = client.get("/api/stocks/600519/margin-trading")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_margin_trading_stock_not_found(self, client):
        resp = client.get("/api/stocks/999999/margin-trading")
        assert resp.status_code == 404

    @patch("app.routers.stocks.get_shareholders_num")
    def test_shareholders_num(self, mock_fn, client):
        self._create_stock(client)
        mock_fn.return_value = [{"date": "2026-01-01", "shareholders_num": 100000}]

        resp = client.get("/api/stocks/600519/shareholders-num")
        assert resp.status_code == 200

    def test_shareholders_num_stock_not_found(self, client):
        resp = client.get("/api/stocks/999999/shareholders-num")
        assert resp.status_code == 404

    @patch("app.routers.stocks.get_customers")
    def test_customers(self, mock_fn, client):
        self._create_stock(client)
        mock_fn.return_value = [{"year": 2025, "name": "客户A"}]

        resp = client.get("/api/stocks/600519/customers")
        assert resp.status_code == 200

    def test_customers_stock_not_found(self, client):
        resp = client.get("/api/stocks/999999/customers")
        assert resp.status_code == 404

    @patch("app.routers.stocks.get_suppliers")
    def test_suppliers(self, mock_fn, client):
        self._create_stock(client)
        mock_fn.return_value = [{"year": 2025, "name": "供应商A"}]

        resp = client.get("/api/stocks/600519/suppliers")
        assert resp.status_code == 200

    def test_suppliers_stock_not_found(self, client):
        resp = client.get("/api/stocks/999999/suppliers")
        assert resp.status_code == 404

    @patch("app.routers.stocks.get_revenue_composition")
    def test_revenue_composition(self, mock_fn, client):
        self._create_stock(client)
        mock_fn.return_value = [{"year": 2025, "segment": "白酒", "ratio": 0.9}]

        resp = client.get("/api/stocks/600519/revenue-composition")
        assert resp.status_code == 200

    def test_revenue_composition_stock_not_found(self, client):
        resp = client.get("/api/stocks/999999/revenue-composition")
        assert resp.status_code == 404
