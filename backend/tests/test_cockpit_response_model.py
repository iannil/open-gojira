"""Test the cockpit endpoint shape.

v2 (2026-06-25): the v1 cockpit_service was orphaned leftover (router never
called it) and has been deleted. The cockpit endpoint is a deliberate v2 stub
pending the Phase-3 signal-first dashboard rebuild. This test pins the stub
contract so a future Phase-3 implementation is a conscious change.
"""

from fastapi.testclient import TestClient
from app.main import app


def test_cockpit_returns_v2_stub():
    client = TestClient(app)
    resp = client.get("/api/cockpit")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "v2_stub"
    assert "Phase 3" in data["message"]
    for key in ("signals", "holdings", "candidates", "watchlist"):
        assert key in data
        assert isinstance(data[key], list)
