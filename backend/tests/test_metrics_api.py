"""Test Phase 6 Tier 1 Metrics API endpoints."""
import pytest


def test_pipeline_metrics_empty(client):
    """无数据时返回结构正确."""
    resp = client.get("/api/metrics/pipelines")
    assert resp.status_code == 200
    data = resp.json()
    assert "pipelines" in data
    assert "overall" in data
    assert data["period_days"] == 30


def test_llm_metrics_empty(client):
    """无数据时返回结构正确."""
    resp = client.get("/api/metrics/llm")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_calls" in data
    assert "total_cost_usd" in data
    assert "conflict_rate_pct" in data
    assert "monthly_cost" in data


def test_llm_trend_empty(client):
    """无数据时返回结构正确."""
    resp = client.get("/api/metrics/llm/trend")
    assert resp.status_code == 200
    data = resp.json()
    assert "labels" in data
    assert "cost_usd" in data


def test_pipeline_metrics_with_days(client):
    """自定义 days 参数."""
    resp = client.get("/api/metrics/pipelines?days=7")
    assert resp.status_code == 200
    assert resp.json()["period_days"] == 7


def test_llm_metrics_with_days(client):
    """自定义 days 参数."""
    resp = client.get("/api/metrics/llm?days=7")
    assert resp.status_code == 200
    assert resp.json()["period_days"] == 7
