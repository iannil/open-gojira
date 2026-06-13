"""Smoke check that the API endpoints resolve correctly."""
from fastapi.testclient import TestClient


def test_api_list_empty(client: TestClient):
    r = client.get("/api/system-alerts")
    assert r.status_code == 200
    assert r.json() == []


def test_api_critical_count_zero(client: TestClient):
    r = client.get("/api/system-alerts/unresolved-count")
    assert r.status_code == 200
    assert r.json() == {"count": 0}


def test_api_resolve_not_found(client: TestClient):
    r = client.post("/api/system-alerts/9999/resolve", json={"resolved_by": "x"})
    assert r.status_code == 404
