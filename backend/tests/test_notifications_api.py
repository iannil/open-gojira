"""Test /api/notifications endpoints.

v2 (decision 19): notification *channels* (email/dingtalk/serverchan + channel
CRUD) were removed — v2 uses in-app SystemAlert notifications only. The router
is a stub; this test pins that contract.
"""


def test_channels_stub_empty(client):
    resp = client.get("/api/notifications/channels")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert data == []


def test_health_ok(client):
    resp = client.get("/api/notifications/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
