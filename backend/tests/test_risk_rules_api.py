"""Test /api/risk-rules endpoints (S5.4)."""

from app.models.stock import Stock


def _seed_stock(db_session, code="600519"):
    db_session.add(Stock(
        code=code, name="贵州茅台", exchange="sh",
        listing_status="normally_listed", prev_close=100.0,
    ))
    db_session.flush()


def test_list_rules_empty(client):
    resp = client.get("/api/risk-rules")
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_rule(client, db_session):
    _seed_stock(db_session)
    resp = client.post("/api/risk-rules", json={
        "stock_code": "600519",
        "stop_loss_pct": 0.08,
        "take_profit_pct": 0.30,
    })
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["stock_code"] == "600519"
    assert data["stop_loss_pct"] == 0.08
    assert data["take_profit_pct"] == 0.30
    assert data["stop_loss_type"] == "pct_from_cost"
    assert data["take_profit_type"] == "pct_from_cost"
    assert data["enabled"] is True
    assert data["triggered_at"] is None
    assert data["id"] is not None


def test_create_rule_defaults(client, db_session):
    _seed_stock(db_session)
    resp = client.post("/api/risk-rules", json={
        "stock_code": "600519",
    })
    assert resp.status_code == 201
    data = resp.json()
    # stop_loss_pct + take_profit_pct default to None
    assert data["stop_loss_pct"] is None
    assert data["take_profit_pct"] is None
    assert data["stop_loss_type"] == "pct_from_cost"


def test_create_rule_duplicate_409(client, db_session):
    _seed_stock(db_session)
    client.post("/api/risk-rules", json={"stock_code": "600519"})
    resp = client.post("/api/risk-rules", json={"stock_code": "600519"})
    assert resp.status_code == 409


def test_get_rule_by_code(client, db_session):
    _seed_stock(db_session)
    r = client.post("/api/risk-rules", json={
        "stock_code": "600519", "stop_loss_pct": 0.08,
    })
    rule_id = r.json()["id"]
    resp = client.get("/api/risk-rules/600519")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == rule_id
    assert data["stop_loss_pct"] == 0.08


def test_get_rule_not_found(client):
    resp = client.get("/api/risk-rules/9999")
    # Returns null with 200 since endpoint is "rule | None"
    assert resp.status_code == 200
    assert resp.json() is None


def test_update_rule(client, db_session):
    _seed_stock(db_session)
    r = client.post("/api/risk-rules", json={
        "stock_code": "600519", "stop_loss_pct": 0.08,
    })
    rule_id = r.json()["id"]
    resp = client.patch(f"/api/risk-rules/{rule_id}", json={
        "stop_loss_pct": 0.10,
        "enabled": False,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["stop_loss_pct"] == 0.10
    assert data["enabled"] is False


def test_update_rule_peak_price_reset(client, db_session):
    """Trailing-stop: peak_price can be reset manually via PATCH."""
    _seed_stock(db_session)
    r = client.post("/api/risk-rules", json={
        "stock_code": "600519",
        "stop_loss_pct": 0.10,
        "stop_loss_type": "trailing",
    })
    rule_id = r.json()["id"]
    resp = client.patch(f"/api/risk-rules/{rule_id}", json={"peak_price": 120.0})
    assert resp.status_code == 200
    assert resp.json()["peak_price"] == 120.0


def test_update_rule_not_found(client):
    resp = client.patch("/api/risk-rules/9999", json={"enabled": False})
    assert resp.status_code == 404


def test_delete_rule(client, db_session):
    _seed_stock(db_session)
    r = client.post("/api/risk-rules", json={"stock_code": "600519"})
    rule_id = r.json()["id"]
    resp = client.delete(f"/api/risk-rules/{rule_id}")
    assert resp.status_code == 204
    # Confirm gone
    resp = client.get("/api/risk-rules")
    assert resp.json() == []


def test_delete_rule_not_found(client):
    resp = client.delete("/api/risk-rules/9999")
    assert resp.status_code == 404


def test_list_rules_multiple(client, db_session):
    _seed_stock(db_session, "600519")
    _seed_stock(db_session, "000001")
    client.post("/api/risk-rules", json={"stock_code": "600519"})
    client.post("/api/risk-rules", json={"stock_code": "000001"})
    resp = client.get("/api/risk-rules")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    # Sorted by stock_code
    assert data[0]["stock_code"] == "000001"
    assert data[1]["stock_code"] == "600519"
