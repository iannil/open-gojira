"""Test that cockpit endpoint returns schema-valid responses."""

from fastapi.testclient import TestClient
from app.main import app


def test_cockpit_returns_valid_schema():
    client = TestClient(app)
    resp = client.get("/api/cockpit")
    assert resp.status_code == 200
    data = resp.json()
    assert "as_of" in data
    assert "holdings" in data
    assert "items" in data["holdings"]
    assert "errors" in data
    assert isinstance(data["errors"], list)
