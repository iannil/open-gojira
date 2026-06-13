"""Test /api/cash endpoints."""

import pytest


def test_get_balance_default_zero(client):
    """When no balance row exists, return 0 and auto-create."""
    resp = client.get("/api/cash/balance")
    assert resp.status_code == 200
    data = resp.json()
    assert data["balance"] == 0.0
    assert data["last_trade_id"] is None
    assert data["last_adjustment_id"] is None


def test_create_deposit_adjustment(client):
    resp = client.post("/api/cash/adjustments", json={
        "amount": 100000.0,
        "happened_at": "2026-06-12T09:00:00",
        "reason": "deposit",
        "note": "Initial capital",
    })
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["amount"] == 100000.0
    assert data["reason"] == "deposit"
    assert data["note"] == "Initial capital"
    assert data["id"] is not None


def test_balance_reflects_adjustment(client):
    client.post("/api/cash/adjustments", json={
        "amount": 500000.0,
        "happened_at": "2026-06-12T09:00:00",
        "reason": "deposit",
    })
    resp = client.get("/api/cash/balance")
    assert resp.json()["balance"] == 500000.0


def test_withdrawal_reduces_balance(client):
    client.post("/api/cash/adjustments", json={
        "amount": 100000.0,
        "happened_at": "2026-06-12T09:00:00",
        "reason": "deposit",
    })
    client.post("/api/cash/adjustments", json={
        "amount": -30000.0,
        "happened_at": "2026-06-12T14:00:00",
        "reason": "withdrawal",
    })
    resp = client.get("/api/cash/balance")
    assert resp.json()["balance"] == 70000.0


def test_list_adjustments(client):
    client.post("/api/cash/adjustments", json={
        "amount": 100000.0,
        "happened_at": "2026-06-11T09:00:00",
        "reason": "deposit",
    })
    client.post("/api/cash/adjustments", json={
        "amount": -10000.0,
        "happened_at": "2026-06-12T14:00:00",
        "reason": "withdrawal",
    })
    resp = client.get("/api/cash/adjustments")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    # newest first
    assert data[0]["happened_at"] >= data[1]["happened_at"]


def test_create_adjustment_invalid_reason(client):
    resp = client.post("/api/cash/adjustments", json={
        "amount": 100.0,
        "happened_at": "2026-06-12T09:00:00",
        "reason": "invalid_reason",
    })
    assert resp.status_code == 422  # pydantic validation


def test_last_adjustment_id_set_on_balance(client):
    r = client.post("/api/cash/adjustments", json={
        "amount": 100.0,
        "happened_at": "2026-06-12T09:00:00",
        "reason": "deposit",
    })
    adj_id = r.json()["id"]
    balance = client.get("/api/cash/balance").json()
    assert balance["last_adjustment_id"] == adj_id
