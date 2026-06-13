"""Test /api/fee-configs endpoints."""

import pytest


def _valid_payload(**overrides):
    payload = {
        "broker_name": "default",
        "commission_rate": 0.00025,
        "commission_min": 5.0,
        "stamp_duty_rate": 0.0005,
        "transfer_fee_rate": 0.00001,
        "effective_from": "2023-10-23",
        "is_active": True,
    }
    payload.update(overrides)
    return payload


def test_create_config(client):
    resp = client.post("/api/fee-configs", json=_valid_payload())
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["broker_name"] == "default"
    assert data["commission_rate"] == 0.00025
    assert data["is_active"] is True
    assert data["id"] is not None


def test_list_configs(client):
    client.post("/api/fee-configs", json=_valid_payload())
    client.post("/api/fee-configs", json=_valid_payload(
        broker_name="huatai",
        effective_from="2024-01-01",
    ))
    resp = client.get("/api/fee-configs")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


def test_list_configs_filter_by_broker(client):
    client.post("/api/fee-configs", json=_valid_payload(broker_name="default"))
    client.post("/api/fee-configs", json=_valid_payload(
        broker_name="huatai",
        effective_from="2024-01-01",
    ))
    resp = client.get("/api/fee-configs?broker_name=huatai")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["broker_name"] == "huatai"


def test_list_configs_filter_by_active(client):
    client.post("/api/fee-configs", json=_valid_payload(is_active=True))
    client.post("/api/fee-configs", json=_valid_payload(
        effective_from="2022-01-01",
        is_active=False,
    ))
    resp = client.get("/api/fee-configs?is_active=true")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["is_active"] is True


def test_update_config(client):
    r = client.post("/api/fee-configs", json=_valid_payload())
    cfg_id = r.json()["id"]
    resp = client.patch(f"/api/fee-configs/{cfg_id}", json={
        "commission_rate": 0.0003,
        "is_active": False,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["commission_rate"] == 0.0003
    assert data["is_active"] is False


def test_update_config_partial(client):
    r = client.post("/api/fee-configs", json=_valid_payload())
    cfg_id = r.json()["id"]
    # Only patch one field
    resp = client.patch(f"/api/fee-configs/{cfg_id}", json={"commission_min": 10.0})
    assert resp.status_code == 200
    data = resp.json()
    assert data["commission_min"] == 10.0
    # Other fields unchanged
    assert data["commission_rate"] == 0.00025


def test_update_config_not_found(client):
    resp = client.patch("/api/fee-configs/9999", json={"commission_min": 10.0})
    assert resp.status_code == 404


def test_delete_config(client):
    r = client.post("/api/fee-configs", json=_valid_payload())
    cfg_id = r.json()["id"]
    resp = client.delete(f"/api/fee-configs/{cfg_id}")
    assert resp.status_code == 204
    # Confirm gone
    resp = client.get("/api/fee-configs")
    assert len(resp.json()) == 0


def test_delete_config_not_found(client):
    resp = client.delete("/api/fee-configs/9999")
    assert resp.status_code == 404


def test_create_config_invalid_commission_rate_too_high(client):
    """commission_rate >= 0.01 (1%) is rejected."""
    resp = client.post("/api/fee-configs", json=_valid_payload(commission_rate=0.05))
    assert resp.status_code == 422
