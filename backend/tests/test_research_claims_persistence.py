"""Tests for Phase 2 #9 research_claims persistence + derivation.

Covers:
- _persist_claims: happy path + required field validation + legacy string fallback
- _validate_stock_codes: A-share 6-digit filtering
- _derive_md: structured → markdown formatting
- Integration with persist_research_result (md field derived from claims)
"""
from __future__ import annotations

import json

import pytest

from app.models.research_claim import ResearchClaim
from app.models.research_run import ResearchRun
from app.models.research_theme import ResearchTheme
from app.services.research_persistence_service import (
    ResearchPersistenceError,
    _derive_md,
    _persist_claims,
    _validate_stock_codes,
)


@pytest.fixture
def run_id(db_session):
    theme = ResearchTheme(name="测试主题", market="A_SHARE", status="active")
    db_session.add(theme)
    db_session.flush()
    run = ResearchRun(
        research_theme_id=theme.id,
        status="completed",
        scope_market="A_SHARE",
        scope_time_window="3-12M",
        triggered_by="test",
        llm_provider="glm-5.1",
    )
    db_session.add(run)
    db_session.flush()
    return run.id


# ── _persist_claims ──────────────────────────────────────────────────────


def test_persist_claims_happy_path(db_session, run_id):
    claims = [
        {
            "subject": "银行IT预算",
            "predicate": "大幅缩减",
            "signal": "订单下滑>20%",
            "outcome": "信创替代放缓",
            "stock_codes": ["300348", "300674"],
            "layer_index": 2,
        },
        {
            "subject": "政策",
            "predicate": "暂停",
            "signal": None,
            "outcome": "需求失效",
            "stock_codes": [],
            "layer_index": None,
        },
    ]
    persisted = _persist_claims(db_session, run_id, claims, "failure_condition")
    assert len(persisted) == 2
    db_session.flush()

    rows = db_session.query(ResearchClaim).filter(
        ResearchClaim.research_run_id == run_id
    ).all()
    assert len(rows) == 2
    assert rows[0].position == 0
    assert rows[0].subject == "银行IT预算"
    assert rows[0].predicate == "大幅缩减"
    assert rows[0].signal == "订单下滑>20%"
    assert rows[0].outcome == "信创替代放缓"
    assert json.loads(rows[0].stock_codes_json) == ["300348", "300674"]
    assert rows[0].layer_index == 2

    assert rows[1].position == 1
    assert rows[1].signal is None
    assert json.loads(rows[1].stock_codes_json) == []
    assert rows[1].layer_index is None


def test_persist_claims_rejects_missing_required(db_session, run_id):
    """subject / predicate / outcome all required."""
    with pytest.raises(ResearchPersistenceError, match="predicate"):
        _persist_claims(
            db_session, run_id,
            [{"subject": "X", "predicate": "", "outcome": "Y"}],
            "failure_condition",
        )


def test_persist_claims_rejects_missing_outcome(db_session, run_id):
    with pytest.raises(ResearchPersistenceError, match="outcome"):
        _persist_claims(
            db_session, run_id,
            [{"subject": "X", "predicate": "Y", "outcome": None}],
            "next_step",
        )


def test_persist_claims_wraps_legacy_string(db_session, run_id):
    """Legacy bare string format triggers warning + wraps (defensive)."""
    persisted = _persist_claims(
        db_session, run_id, ["legacy bare text"], "failure_condition",
    )
    assert len(persisted) == 1
    # subject/predicate are placeholders, outcome carries the original text
    assert persisted[0].subject == "(未结构化)"
    assert persisted[0].predicate == "(legacy)"
    assert persisted[0].outcome == "legacy bare text"


def test_persist_claims_invalid_layer_index_falls_back_to_none(
    db_session, run_id, caplog,
):
    """layer_index outside 1-8 logged and set to None."""
    persisted = _persist_claims(
        db_session, run_id,
        [{
            "subject": "X", "predicate": "Y", "outcome": "Z",
            "layer_index": 99,
        }],
        "failure_condition",
    )
    assert persisted[0].layer_index is None


# ── _validate_stock_codes ────────────────────────────────────────────────


def test_validate_stock_codes_keeps_6_digit():
    assert _validate_stock_codes(["300348", "002049", "600519"]) == [
        "300348", "002049", "600519"
    ]


def test_validate_stock_codes_drops_non_6_digit():
    assert _validate_stock_codes(["123", "1234567", "abc123", "300348"]) == [
        "300348"
    ]


def test_validate_stock_codes_handles_none():
    assert _validate_stock_codes(None) == []


def test_validate_stock_codes_handles_empty_list():
    assert _validate_stock_codes([]) == []


def test_validate_stock_codes_handles_non_list():
    assert _validate_stock_codes("300348") == []


# ── _derive_md ───────────────────────────────────────────────────────────


def test_derive_md_full_fields():
    claims = [
        ResearchClaim(
            research_run_id=1, type="failure_condition", position=0,
            subject="银行IT预算", predicate="大幅缩减",
            signal="订单下滑>20%", outcome="信创替代放缓",
            stock_codes_json="[]", layer_index=2,
        ),
    ]
    md = _derive_md(claims)
    assert md == "1. 银行IT预算大幅缩减(订单下滑>20%),信创替代放缓"


def test_derive_md_without_signal():
    claims = [
        ResearchClaim(
            research_run_id=1, type="next_step", position=0,
            subject="年报", predicate="查阅",
            signal=None, outcome="验证业务",
            stock_codes_json="[]", layer_index=None,
        ),
    ]
    md = _derive_md(claims)
    assert md == "1. 年报查阅,验证业务"


def test_derive_md_multiple_claims_positioned():
    claims = [
        ResearchClaim(
            research_run_id=1, type="failure_condition", position=0,
            subject="A", predicate="B", signal=None, outcome="C",
            stock_codes_json="[]", layer_index=None,
        ),
        ResearchClaim(
            research_run_id=1, type="failure_condition", position=1,
            subject="D", predicate="E", signal=None, outcome="F",
            stock_codes_json="[]", layer_index=None,
        ),
    ]
    md = _derive_md(claims)
    assert md == "1. AB,C\n2. DE,F"


def test_derive_md_empty_list_returns_empty():
    assert _derive_md([]) == ""
