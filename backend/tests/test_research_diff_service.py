"""Tests for research_diff_service — Phase 2 #10.

Covers:
- compute_diff happy path (3 dimensions all populated)
- _diff_ranking: 5 buckets (promoted/demoted/new_in/dropped/unchanged) + sort
- _diff_claims: subject matching + signal change detection + legacy degradation
- _diff_scarce_layers: layer_ref_id keyed + entered/exited/reranked/unchanged
- compute_diff: per-dimension failure isolation
- compute_diff: run order normalization (run_a earlier, run_b later)
"""
from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.models.research_claim import ResearchClaim
from app.models.research_company_ranking import ResearchCompanyRanking
from app.models.research_run import ResearchRun
from app.models.research_theme import ResearchTheme
from app.models.scarce_layer import ScarceLayer
from app.models.value_chain_layer import ValueChainLayer
from app.services.research_diff_service import (
    ClaimsDiff,
    DiffError,
    RankingDiff,
    ScarceLayerDiff,
    _diff_claims,
    _diff_ranking,
    _diff_scarce_layers,
    compute_diff,
)


@pytest.fixture
def theme(db_session):
    t = ResearchTheme(name="测试主题", market="A_SHARE", status="active")
    db_session.add(t)
    db_session.flush()
    return t


def _make_run(db_session, theme_id, *, started_offset_min=0, status="completed"):
    run = ResearchRun(
        research_theme_id=theme_id,
        status=status,
        scope_market="A_SHARE",
        scope_time_window="3-12M",
        triggered_by="test",
        llm_provider="glm-5.1",
        started_at=datetime.utcnow() - timedelta(minutes=started_offset_min),
    )
    db_session.add(run)
    db_session.flush()
    return run


def _add_ranking(db_session, run_id, stock_code, rank):
    # ResearchCompanyRanking has no `name` field (persist drops it)
    db_session.add(ResearchCompanyRanking(
        research_run_id=run_id, rank=rank, stock_code=stock_code,
        constrains_what="环节", chain_position="位置",
        rank_reason_md="原因", evidence_summary_md="证据", main_risk_md="风险",
    ))


def _add_layer(db_session, run_id, layer_index, name):
    vcl = ValueChainLayer(
        research_run_id=run_id, layer_index=layer_index, name=name,
        description="描述",
    )
    db_session.add(vcl)
    db_session.flush()
    return vcl


def _add_scarce(db_session, run_id, rank, layer_ref_id):
    db_session.add(ScarceLayer(
        research_run_id=run_id, rank=rank, layer_ref_id=layer_ref_id,
        scarcity_reason_md="原因", expansion_difficulty="high",
    ))


def _add_claim(
    db_session, run_id, position, subject, predicate="", signal=None,
    outcome="", stock_codes=None, layer_index=None,
):
    import json
    db_session.add(ResearchClaim(
        research_run_id=run_id, type="failure_condition", position=position,
        subject=subject, predicate=predicate, signal=signal, outcome=outcome,
        stock_codes_json=json.dumps(stock_codes or []),
        layer_index=layer_index,
    ))


# ── _diff_ranking ────────────────────────────────────────────────────────


def test_diff_ranking_classifies_all_5_buckets(db_session, theme):
    a = _make_run(db_session, theme.id, started_offset_min=120)
    b = _make_run(db_session, theme.id, started_offset_min=0)

    # 002049: rank 1 → 1 (unchanged)
    # 300348: rank 2 → 1 (promoted, delta=-1)
    # 600036: rank 3 → 4 (demoted, delta=+1)
    # 002152: rank 4 → dropped
    # 600519: not in a, rank 5 in b (new_in)
    for code, rank in [("002049", 1), ("300348", 2), ("600036", 3), ("002152", 4)]:
        _add_ranking(db_session, a.id, code, rank)
    for code, rank in [("002049", 1), ("300348", 1), ("600036", 4), ("600519", 5)]:
        _add_ranking(db_session, b.id, code, rank)
    db_session.flush()

    result = _diff_ranking(db_session, a.id, b.id)
    assert len(result.unchanged) == 1
    assert len(result.promoted) == 1
    assert len(result.demoted) == 1
    assert len(result.dropped) == 1
    assert len(result.new_in) == 1

    assert result.promoted[0].stock_code == "300348"
    assert result.promoted[0].delta == -1
    assert result.demoted[0].stock_code == "600036"
    assert result.demoted[0].delta == 1
    assert result.new_in[0].stock_code == "600519"
    assert result.dropped[0].stock_code == "002152"
    assert result.unchanged[0].stock_code == "002049"


def test_diff_ranking_empty_runs(db_session, theme):
    a = _make_run(db_session, theme.id, started_offset_min=120)
    b = _make_run(db_session, theme.id, started_offset_min=0)
    result = _diff_ranking(db_session, a.id, b.id)
    assert result.promoted == [] and result.demoted == []
    assert result.new_in == [] and result.dropped == []
    assert result.unchanged == []


# ── _diff_claims ─────────────────────────────────────────────────────────


def test_diff_claims_classifies_4_buckets(db_session, theme):
    a = _make_run(db_session, theme.id, started_offset_min=120)
    b = _make_run(db_session, theme.id, started_offset_min=0)

    # 4 claims in A, 4 in B
    # "净息差" signal 变化 → tightened
    # "数字人民币" A only → resolved
    # "房地产风险" B only → new_risk
    # "信创替代进度" unchanged
    _add_claim(db_session, a.id, 0, "净息差", predicate="<", signal="<1.5%",
               outcome="逻辑失效", stock_codes=["600036"])
    _add_claim(db_session, a.id, 1, "数字人民币", predicate="放缓",
               signal=None, outcome="需求弱化")
    _add_claim(db_session, a.id, 2, "信创替代进度", predicate="放缓",
               signal=None, outcome="订单下滑")

    _add_claim(db_session, b.id, 0, "净息差", predicate="<", signal="<1.8%",
               outcome="逻辑失效", stock_codes=["600036"])
    _add_claim(db_session, b.id, 1, "房地产风险", predicate="爆发",
               signal="不良率>5%", outcome="资产质量恶化")
    _add_claim(db_session, b.id, 2, "信创替代进度", predicate="放缓",
               signal=None, outcome="订单下滑")
    db_session.flush()

    result = _diff_claims(db_session, a.id, b.id)
    assert len(result.tightened) == 1
    assert len(result.resolved) == 1
    assert len(result.new_risks) == 1
    assert len(result.unchanged) == 1

    assert result.tightened[0].subject == "净息差"
    assert result.tightened[0].signal_changed is True
    assert result.resolved[0].subject == "数字人民币"
    assert result.new_risks[0].subject == "房地产风险"
    assert result.unchanged[0].subject == "信创替代进度"


def test_diff_claims_raises_legacy_when_a_has_no_claims(db_session, theme):
    """Legacy run A (pre-Phase-2-#9) has zero claims → _LegacyRunError."""
    a = _make_run(db_session, theme.id, started_offset_min=120)
    b = _make_run(db_session, theme.id, started_offset_min=0)
    _add_claim(db_session, b.id, 0, "X", predicate="Y", signal=None, outcome="Z")
    db_session.flush()

    from app.services.research_diff_service import _LegacyRunError
    with pytest.raises(_LegacyRunError, match="run.*no structured claims"):
        _diff_claims(db_session, a.id, b.id)


def test_diff_claims_raises_legacy_when_both_empty(db_session, theme):
    a = _make_run(db_session, theme.id, started_offset_min=120)
    b = _make_run(db_session, theme.id, started_offset_min=0)

    from app.services.research_diff_service import _LegacyRunError
    with pytest.raises(_LegacyRunError, match="both runs"):
        _diff_claims(db_session, a.id, b.id)


# ── _diff_scarce_layers ──────────────────────────────────────────────────


def test_diff_scarce_layers_classifies_4_buckets(db_session, theme):
    a = _make_run(db_session, theme.id, started_offset_min=120)
    b = _make_run(db_session, theme.id, started_offset_min=0)

    # Use SAME layer_index+name in both runs (via separate VCL rows since
    # VCL is per-run). Layer 4 enters in B only, layer 7 exits in B.
    vcl_a1 = _add_layer(db_session, a.id, 2, "系统集成")
    vcl_a2 = _add_layer(db_session, a.id, 4, "芯片器件")
    vcl_a3 = _add_layer(db_session, a.id, 7, "材料耗材")

    vcl_b1 = _add_layer(db_session, b.id, 2, "系统集成")
    vcl_b2 = _add_layer(db_session, b.id, 4, "芯片器件")
    vcl_b3 = _add_layer(db_session, b.id, 5, "IT基础设施")

    # A: layer2 rank=1, layer4 rank=2, layer7 rank=3
    _add_scarce(db_session, a.id, 1, vcl_a1.id)
    _add_scarce(db_session, a.id, 2, vcl_a2.id)
    _add_scarce(db_session, a.id, 3, vcl_a3.id)
    # B: layer2 rank=1, layer4 rank=3, layer5 rank=2 (reranked: layer4 from 2→3,
    # entered: layer5, exited: layer7)
    _add_scarce(db_session, b.id, 1, vcl_b1.id)
    _add_scarce(db_session, b.id, 3, vcl_b2.id)
    _add_scarce(db_session, b.id, 2, vcl_b3.id)
    db_session.flush()

    result = _diff_scarce_layers(db_session, a.id, b.id)
    assert len(result.unchanged) == 1  # layer2 (rank 1→1)
    assert len(result.reranked) == 1   # layer4 (rank 2→3)
    assert len(result.entered) == 1    # layer5 (new)
    assert len(result.exited) == 1     # layer7 (dropped)


# ── compute_diff ─────────────────────────────────────────────────────────


def test_compute_diff_normalizes_run_order(db_session, theme):
    """Caller passes (newer, older) → service swaps to (older, newer)."""
    older = _make_run(db_session, theme.id, started_offset_min=120)
    newer = _make_run(db_session, theme.id, started_offset_min=0)

    # Pass in "wrong" order
    result = compute_diff(db_session, newer.id, older.id)
    assert result.run_a.id == older.id
    assert result.run_b.id == newer.id


def test_compute_diff_includes_summary_counts(db_session, theme):
    a = _make_run(db_session, theme.id, started_offset_min=120)
    b = _make_run(db_session, theme.id, started_offset_min=0)

    _add_ranking(db_session, a.id, "002049", 1)
    _add_ranking(db_session, b.id, "002049", 1)
    _add_ranking(db_session, b.id, "300348", 2)

    _add_claim(db_session, a.id, 0, "净息差", predicate="<", signal="<1.5%",
               outcome="逻辑失效")
    _add_claim(db_session, b.id, 0, "净息差", predicate="<", signal="<1.8%",
               outcome="逻辑失效")
    db_session.flush()

    result = compute_diff(db_session, a.id, b.id)
    assert result.summary["ranking"]["unchanged"] == 1
    assert result.summary["ranking"]["new_in"] == 1
    assert result.summary["claims"]["tightened"] == 1
    assert result.summary["scarce_layers"]["unchanged"] == 0


def test_compute_diff_degrades_for_legacy_run(db_session, theme):
    """Legacy run (no structured claims) → claims_diff=null + degradation."""
    a = _make_run(db_session, theme.id, started_offset_min=120)
    b = _make_run(db_session, theme.id, started_offset_min=0)

    _add_ranking(db_session, a.id, "002049", 1)
    _add_ranking(db_session, b.id, "002049", 1)
    # No claims in A (legacy)
    _add_claim(db_session, b.id, 0, "净息差", predicate="<", signal="<1.5%",
               outcome="逻辑失效")
    db_session.flush()

    result = compute_diff(db_session, a.id, b.id)
    assert result.claims_diff is None
    assert any("claims_diff_unavailable_legacy" in d for d in result.degradations)
    # Other dimensions still populated
    assert result.ranking_diff is not None
    assert result.scarce_layers_diff is not None


def test_compute_diff_not_found_raises(db_session, theme):
    a = _make_run(db_session, theme.id, started_offset_min=0)
    with pytest.raises(DiffError, match="not found"):
        compute_diff(db_session, a.id, 99999)


def test_compute_diff_isolates_per_dimension_failures(
    db_session, theme, monkeypatch,
):
    """A dimension raising unexpectedly → degraded flag, others still work."""
    a = _make_run(db_session, theme.id, started_offset_min=120)
    b = _make_run(db_session, theme.id, started_offset_min=0)

    _add_ranking(db_session, a.id, "002049", 1)
    _add_ranking(db_session, b.id, "002049", 1)
    _add_claim(db_session, a.id, 0, "净息差", predicate="<", signal="<1.5%",
               outcome="X")
    _add_claim(db_session, b.id, 0, "净息差", predicate="<", signal="<1.8%",
               outcome="X")
    db_session.flush()

    def boom(*args, **kwargs):
        raise RuntimeError("simulated algorithm bug")
    monkeypatch.setattr(
        "app.services.research_diff_service._diff_scarce_layers", boom
    )

    result = compute_diff(db_session, a.id, b.id)
    assert result.ranking_diff is not None
    assert result.claims_diff is not None
    # scarce_layers_diff degraded to empty
    assert result.scarce_layers_diff.entered == []
    assert any("scarce_layers_diff_failed" in d for d in result.degradations)
