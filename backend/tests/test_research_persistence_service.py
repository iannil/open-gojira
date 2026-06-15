"""Tests for research persistence service.

Covers schema validation + 6-table writes + FK integrity.
"""
from __future__ import annotations

import pytest

from app.models.research_evidence import ResearchEvidence
from app.models.research_company_ranking import ResearchCompanyRanking
from app.models.research_company_universe import ResearchCompanyUniverse
from app.models.research_run import ResearchRun
from app.models.research_theme import ResearchTheme
from app.models.scarce_layer import ScarceLayer
from app.models.stock import Stock
from app.models.value_chain_layer import ValueChainLayer
from app.services.research_persistence_service import (
    ResearchPersistenceError,
    persist_research_result,
)


@pytest.fixture
def setup_theme_and_stock(db_session):
    """Seed one ResearchTheme + one Stock for FK."""
    theme = ResearchTheme(name="测试主题", market="A_SHARE")
    db_session.add(theme)
    stock = Stock(code="300001", name="测试股票")
    db_session.add(stock)
    db_session.flush()
    return theme, stock


@pytest.fixture
def valid_llm_output():
    """Minimal valid LLM output that passes all schema checks."""
    return {
        "system_change": "AI 需求驱动内存互连升级",
        "value_chain": [
            {"layer_index": i, "name": f"层{i}", "description": f"描述{i}"}
            for i in range(1, 9)
        ],
        "scarce_layers": [
            {"rank": 1, "layer_index": 4, "reason": "客户数低", "difficulty": "high"},
            {"rank": 2, "layer_index": 5, "reason": "认证慢", "difficulty": "medium"},
            {"rank": 3, "layer_index": 7, "reason": "材料纯度", "difficulty": "high"},
        ],
        "company_universe": [
            {"stock_code": "300001", "name": f"公司{i}", "classification": "controls",
             "layer_index": 4, "note": f"备注{i}"}
            for i in range(25)  # ≥20
        ],
        "evidence": [
            {"source_url": f"http://e{i}.example", "source_title": f"证据{i}",
             "source_type": "filing", "grade": "strong", "summary": f"摘要{i}",
             "stock_code": "300001"}
            for i in range(30)  # ≥25
        ],
        "company_ranking": [
            {"rank": i, "stock_code": "300001", "name": f"公司{i}",
             "constrains_what": f"环节{i}", "chain_position": f"位置{i}",
             "rank_reason": f"原因{i}", "evidence_summary": f"证据{i}",
             "main_risk": f"风险{i}"}
            for i in range(1, 6)  # 3-7
        ],
        "failure_conditions": ["需求放缓", "竞品扩产", "估值已涨"],
        "next_steps": ["查年报", "查订单", "查客户认证"],
    }


def test_persist_full_valid_output(db_session, setup_theme_and_stock, valid_llm_output):
    """Q3 D: 6-table persistence happy path."""
    theme, _ = setup_theme_and_stock
    run = ResearchRun(research_theme_id=theme.id, status="running",
                      scope_market="A_SHARE", scope_time_window="3-12M",
                      triggered_by="manual", llm_provider="glm-4.7")
    db_session.add(run)
    db_session.flush()

    persist_research_result(db_session, run, valid_llm_output)

    layers = db_session.query(ValueChainLayer).all()
    scarce = db_session.query(ScarceLayer).all()
    universe = db_session.query(ResearchCompanyUniverse).all()
    evidence = db_session.query(ResearchEvidence).all()
    ranking = db_session.query(ResearchCompanyRanking).all()

    assert len(layers) == 8
    assert len(scarce) == 3
    assert len(universe) == 25
    assert len(evidence) == 30
    assert len(ranking) == 5

    # Markdown fields populated
    assert run.system_change_md == "AI 需求驱动内存互连升级"
    assert "需求放缓" in run.failure_conditions_md
    assert "查年报" in run.next_steps_md


def test_persist_rejects_insufficient_companies(db_session, setup_theme_and_stock, valid_llm_output):
    """Schema validation: < 20 companies rejected."""
    theme, _ = setup_theme_and_stock
    run = ResearchRun(research_theme_id=theme.id, status="running",
                      scope_market="A_SHARE", scope_time_window="3-12M",
                      triggered_by="manual", llm_provider="glm-4.7")
    db_session.add(run)
    db_session.flush()

    valid_llm_output["company_universe"] = valid_llm_output["company_universe"][:15]
    with pytest.raises(ResearchPersistenceError, match=r"≥20"):
        persist_research_result(db_session, run, valid_llm_output)


def test_persist_rejects_insufficient_evidence(db_session, setup_theme_and_stock, valid_llm_output):
    """Schema validation: < 25 evidence rejected."""
    theme, _ = setup_theme_and_stock
    run = ResearchRun(research_theme_id=theme.id, status="running",
                      scope_market="A_SHARE", scope_time_window="3-12M",
                      triggered_by="manual", llm_provider="glm-4.7")
    db_session.add(run)
    db_session.flush()

    valid_llm_output["evidence"] = valid_llm_output["evidence"][:20]
    with pytest.raises(ResearchPersistenceError, match=r"≥25"):
        persist_research_result(db_session, run, valid_llm_output)


def test_persist_rejects_wrong_value_chain_length(db_session, setup_theme_and_stock, valid_llm_output):
    """Schema validation: value_chain must be exactly 8 layers."""
    theme, _ = setup_theme_and_stock
    run = ResearchRun(research_theme_id=theme.id, status="running",
                      scope_market="A_SHARE", scope_time_window="3-12M",
                      triggered_by="manual", llm_provider="glm-4.7")
    db_session.add(run)
    db_session.flush()

    valid_llm_output["value_chain"] = valid_llm_output["value_chain"][:7]
    with pytest.raises(ResearchPersistenceError, match=r"exactly 8"):
        persist_research_result(db_session, run, valid_llm_output)


def test_persist_rejects_wrong_ranking_count(db_session, setup_theme_and_stock, valid_llm_output):
    """Schema validation: ranking must be 3-7."""
    theme, _ = setup_theme_and_stock
    run = ResearchRun(research_theme_id=theme.id, status="running",
                      scope_market="A_SHARE", scope_time_window="3-12M",
                      triggered_by="manual", llm_provider="glm-4.7")
    db_session.add(run)
    db_session.flush()

    valid_llm_output["company_ranking"] = valid_llm_output["company_ranking"][:2]
    with pytest.raises(ResearchPersistenceError, match=r"3-7"):
        persist_research_result(db_session, run, valid_llm_output)


def test_persist_rejects_unknown_layer_index_in_scarce(db_session, setup_theme_and_stock, valid_llm_output):
    """FK integrity: scarce_layer.layer_index must exist in value_chain."""
    theme, _ = setup_theme_and_stock
    run = ResearchRun(research_theme_id=theme.id, status="running",
                      scope_market="A_SHARE", scope_time_window="3-12M",
                      triggered_by="manual", llm_provider="glm-4.7")
    db_session.add(run)
    db_session.flush()

    valid_llm_output["scarce_layers"][0]["layer_index"] = 99  # out of range
    with pytest.raises(ResearchPersistenceError, match=r"unknown layer_index"):
        persist_research_result(db_session, run, valid_llm_output)


def test_persist_rejects_missing_required_field(db_session, setup_theme_and_stock, valid_llm_output):
    """Schema validation: missing top-level field rejected."""
    theme, _ = setup_theme_and_stock
    run = ResearchRun(research_theme_id=theme.id, status="running",
                      scope_market="A_SHARE", scope_time_window="3-12M",
                      triggered_by="manual", llm_provider="glm-4.7")
    db_session.add(run)
    db_session.flush()

    del valid_llm_output["system_change"]
    with pytest.raises(ResearchPersistenceError, match=r"system_change"):
        persist_research_result(db_session, run, valid_llm_output)
