"""Tests for research router endpoints.

Covers CRUD + trigger + export + appearances.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


def test_list_empty_themes(client):
    """GET /api/research/themes returns empty when no themes."""
    res = client.get("/api/research/themes")
    assert res.status_code == 200
    assert res.json() == []


def test_create_theme_and_get(client):
    """POST + GET theme."""
    payload = {
        "name": "AI 半导体",
        "description": "测试主题",
        "market": "A_SHARE",
        "auto_refresh_freq": "manual",
    }
    res = client.post("/api/research/themes", json=payload)
    assert res.status_code == 201
    theme = res.json()
    assert theme["name"] == "AI 半导体"
    assert theme["status"] == "active"

    res2 = client.get(f"/api/research/themes/{theme['id']}")
    assert res2.status_code == 200
    assert res2.json()["name"] == "AI 半导体"


def test_update_theme(client, db_session):
    """PUT updates fields."""
    from app.models.research_theme import ResearchTheme
    theme = ResearchTheme(name="原", market="A_SHARE")
    db_session.add(theme); db_session.flush()

    res = client.put(
        f"/api/research/themes/{theme.id}",
        json={"description": "新描述", "auto_refresh_freq": "weekly"},
    )
    assert res.status_code == 200
    assert res.json()["description"] == "新描述"
    assert res.json()["auto_refresh_freq"] == "weekly"


def test_archive_theme_soft_delete(client, db_session):
    """DELETE archives (status=archived), does not remove row."""
    from app.models.research_theme import ResearchTheme
    theme = ResearchTheme(name="归档测试", market="A_SHARE", status="active")
    db_session.add(theme); db_session.flush()

    res = client.delete(f"/api/research/themes/{theme.id}")
    assert res.status_code == 200
    assert res.json()["ok"] is True

    db_session.expire_all()
    refreshed = db_session.query(ResearchTheme).filter(ResearchTheme.id == theme.id).first()
    assert refreshed.status == "archived"


def test_trigger_run_unknown_theme_404(client):
    """POST /themes/{id}/run on unknown id returns 404."""
    res = client.post("/api/research/themes/99999/run", json={})
    assert res.status_code == 409  # ResearchRunnerError → 409


def test_trigger_run_rate_limited_returns_409(client, db_session):
    """Q6: rate limit returns 409 (conflict)."""
    from datetime import datetime
    from app.models.research_theme import ResearchTheme
    theme = ResearchTheme(
        name="限频", market="A_SHARE", status="active",
        last_run_at=datetime.utcnow(),
    )
    db_session.add(theme); db_session.flush()

    res = client.post(f"/api/research/themes/{theme.id}/run", json={})
    assert res.status_code == 409
    assert "wait" in res.json()["detail"].lower()


def test_list_runs_for_theme(client, db_session):
    """GET /themes/{id}/runs returns run history."""
    from app.models.research_run import ResearchRun
    from app.models.research_theme import ResearchTheme
    theme = ResearchTheme(name="历史", market="A_SHARE")
    db_session.add(theme); db_session.flush()
    for _ in range(3):
        db_session.add(ResearchRun(
            research_theme_id=theme.id, status="completed",
            scope_market="A_SHARE", scope_time_window="3-12M",
            triggered_by="manual", llm_provider="glm-4.7",
        ))
    db_session.flush()

    res = client.get(f"/api/research/themes/{theme.id}/runs")
    assert res.status_code == 200
    assert len(res.json()) == 3


def test_get_run_404(client):
    """GET /runs/{id} on unknown id returns 404."""
    res = client.get("/api/research/runs/99999")
    assert res.status_code == 404


def test_export_run_phase2_supports_candidate(client, db_session):
    """Phase 2: target=candidate via plan_id nullable (s2 migration)."""
    from app.models.candidate import Candidate
    from app.models.research_company_ranking import ResearchCompanyRanking
    from app.models.research_run import ResearchRun
    from app.models.research_theme import ResearchTheme
    from app.models.stock import Stock
    theme = ResearchTheme(name="导出", market="A_SHARE")
    db_session.add(theme); db_session.flush()
    run = ResearchRun(
        research_theme_id=theme.id, status="completed",
        scope_market="A_SHARE", scope_time_window="3-12M",
        triggered_by="manual", llm_provider="glm-4.7",
    )
    db_session.add(run); db_session.flush()
    db_session.add(Stock(code="300001", name="测试"))
    db_session.flush()
    db_session.add(ResearchCompanyRanking(
        research_run_id=run.id, rank=1, stock_code="300001",
        constrains_what="环节", chain_position="层4",
        rank_reason_md="原因", evidence_summary_md="证据", main_risk_md="风险",
    ))
    db_session.flush()

    res = client.post(
        f"/api/research/runs/{run.id}/export",
        json={"target": "candidate", "rank_max": 1},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["exported_count"] == 1
    assert body["target"] == "candidate"
    assert body["target_id"] is None  # plan_id nullable, no sentinel

    # Verify candidate was actually written with source='serenity', plan_id=None
    candidates = (
        db_session.query(Candidate)
        .filter(Candidate.source == "serenity")
        .all()
    )
    assert len(candidates) == 1
    assert candidates[0].plan_id is None


def test_appearances_empty_for_unknown_stock(client):
    """GET /appearances/{code} returns [] for unknown stock."""
    res = client.get("/api/research/appearances/999999")
    assert res.status_code == 200
    assert res.json() == []


def test_appearances_returns_universe_and_ranking(client, db_session):
    """Q14: reverse-link joins universe + ranking + run + theme."""
    from app.models.research_company_ranking import ResearchCompanyRanking
    from app.models.research_company_universe import ResearchCompanyUniverse
    from app.models.research_run import ResearchRun
    from app.models.research_theme import ResearchTheme
    from app.models.stock import Stock

    stock = Stock(code="300001", name="测试")
    db_session.add(stock)
    theme = ResearchTheme(name="链接", market="A_SHARE")
    db_session.add(theme); db_session.flush()
    run = ResearchRun(
        research_theme_id=theme.id, status="completed",
        scope_market="A_SHARE", scope_time_window="3-12M",
        triggered_by="manual", llm_provider="glm-4.7",
    )
    db_session.add(run); db_session.flush()
    db_session.add(ResearchCompanyUniverse(
        research_run_id=run.id, stock_code="300001",
        classification="controls",
    ))
    db_session.add(ResearchCompanyRanking(
        research_run_id=run.id, rank=2, stock_code="300001",
        constrains_what="内存互连", chain_position="层4",
        rank_reason_md="带宽升级绕不开", evidence_summary_md="季报互连收入",
        main_risk_md="迭代放缓",
    ))
    db_session.flush()

    res = client.get("/api/research/appearances/300001")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["research_theme_name"] == "链接"
    assert data[0]["rank"] == 2
    assert data[0]["classification"] == "controls"
    assert data[0]["constrains_what"] == "内存互连"
