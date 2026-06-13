"""Test /api/notifications endpoints (S5.4)."""

from unittest.mock import patch


def test_list_channels_empty(client):
    resp = client.get("/api/notifications/channels")
    assert resp.status_code == 200
    # Empty by default — no seeding in test conftest
    assert isinstance(resp.json(), list)


def test_create_channel(client):
    resp = client.post("/api/notifications/channels", json={
        "name": "test_sc",
        "type": "server_chan",
        "config_json": {"sendkey": "SCT123"},
    })
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["name"] == "test_sc"
    assert data["type"] == "server_chan"
    assert data["config_json"] == {"sendkey": "SCT123"}
    assert data["enabled"] is True
    assert data["severity_filter"] == "all"
    assert data["id"] is not None


def test_create_channel_with_options(client):
    resp = client.post("/api/notifications/channels", json={
        "name": "email_critical",
        "type": "email",
        "config_json": {"to": "user@example.com"},
        "enabled": False,
        "severity_filter": "critical_only",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["enabled"] is False
    assert data["severity_filter"] == "critical_only"


def test_list_channels_after_create(client):
    client.post("/api/notifications/channels", json={
        "name": "ch1", "type": "server_chan", "config_json": {"sendkey": "k1"},
    })
    client.post("/api/notifications/channels", json={
        "name": "ch2", "type": "email",
        "config_json": {"to": "a@b.com"}, "enabled": False,
    })
    resp = client.get("/api/notifications/channels")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


def test_list_channels_enabled_only(client):
    client.post("/api/notifications/channels", json={
        "name": "ch1", "type": "server_chan", "config_json": {},
        "enabled": True,
    })
    client.post("/api/notifications/channels", json={
        "name": "ch2", "type": "email", "config_json": {},
        "enabled": False,
    })
    resp = client.get("/api/notifications/channels?enabled_only=true")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "ch1"


def test_update_channel(client):
    r = client.post("/api/notifications/channels", json={
        "name": "test", "type": "email", "config_json": {"to": "a@b.com"},
    })
    channel_id = r.json()["id"]
    resp = client.patch(f"/api/notifications/channels/{channel_id}",
                         json={"enabled": False})
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is False


def test_update_channel_partial(client):
    r = client.post("/api/notifications/channels", json={
        "name": "test", "type": "email",
        "config_json": {"to": "a@b.com"},
        "severity_filter": "critical_only",
    })
    channel_id = r.json()["id"]
    # Patch only severity_filter
    resp = client.patch(f"/api/notifications/channels/{channel_id}",
                         json={"severity_filter": "all"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["severity_filter"] == "all"
    # Other fields unchanged
    assert data["enabled"] is True


def test_update_channel_not_found(client):
    resp = client.patch("/api/notifications/channels/9999",
                         json={"enabled": False})
    assert resp.status_code == 404


def test_delete_channel(client):
    r = client.post("/api/notifications/channels", json={
        "name": "todelete", "type": "email", "config_json": {},
    })
    cid = r.json()["id"]
    resp = client.delete(f"/api/notifications/channels/{cid}")
    assert resp.status_code == 204
    # Confirm gone
    resp = client.get("/api/notifications/channels")
    assert len(resp.json()) == 0


def test_delete_channel_not_found(client):
    resp = client.delete("/api/notifications/channels/9999")
    assert resp.status_code == 404


def test_test_channel_in_app_always_succeeds(client):
    """in_app channel always returns success — no network call."""
    r = client.post("/api/notifications/channels", json={
        "name": "in_app", "type": "in_app", "config_json": {},
    })
    cid = r.json()["id"]
    resp = client.post(f"/api/notifications/test/{cid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True


def test_test_channel_not_found(client):
    resp = client.post("/api/notifications/test/9999")
    assert resp.status_code == 404


def test_test_channel_server_chan_calls_external(client):
    """Test endpoint should call _send_server_chan."""
    r = client.post("/api/notifications/channels", json={
        "name": "sc", "type": "server_chan",
        "config_json": {"sendkey": "SCT123"},
    })
    cid = r.json()["id"]
    with patch("app.services.notification_service._send_server_chan") as sc:
        sc.return_value = True
        resp = client.post(f"/api/notifications/test/{cid}")
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    sc.assert_called_once()
