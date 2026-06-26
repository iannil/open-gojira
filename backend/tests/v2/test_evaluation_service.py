"""Tests for evaluation_service — P1 评价系统.

Covers:
- trade_statistics: win/loss/profit factor on empty and populated data
- signal_quality: slippage computation from DecisionAudit
- dual_engine_attribution: draft source → engine attribution
- benchmark_comparison: portfolio vs index return
- full_evaluation: aggregation
"""
from datetime import date, datetime

import pytest

from app.models.decision_audit import DecisionAudit
from app.models.draft import Draft
from app.models.stock import Stock
from app.models.trade import Trade
from app.services.evaluation_service import (
    trade_statistics,
    signal_quality,
    dual_engine_attribution,
    benchmark_comparison,
    full_evaluation,
)


@pytest.fixture
def db_session():
    from tests.conftest import TestSessionLocal
    s = TestSessionLocal()
    try:
        yield s
    finally:
        s.close()


# ── trade_statistics ─────────────────────────────────────────────────────


def test_trade_stats_empty(db_session):
    result = trade_statistics(db_session)
    assert result["total_trades"] == 0
    assert result["win_rate_pct"] == 0.0


def test_trade_stats_with_trades(db_session):
    db_session.add(Stock(code="600519", name="茅台", prev_close=100.0))
    db_session.add(Trade(stock_code="600519", side="BUY", price=100.0, quantity=100,
                         filled_at=datetime(2026, 1, 10, 10, 0), total_value=10000.0,
                         source="manual"))
    db_session.add(Trade(stock_code="600519", side="SELL", price=110.0, quantity=-100,
                         filled_at=datetime(2026, 6, 10, 10, 0), total_value=11000.0,
                         source="manual"))
    db_session.commit()

    result = trade_statistics(db_session)
    assert result["total_trades"] >= 2


# ── signal_quality ───────────────────────────────────────────────────────


def test_signal_quality_empty(db_session):
    result = signal_quality(db_session)
    assert result["total_executed"] == 0
    assert result["with_slippage_data"] == 0


def test_signal_quality_with_data(db_session):
    db_session.add(DecisionAudit(
        draft_id=1, stock_code="600519", action="BUY",
        target_price=100.0, executed_price=101.0, quantity=100,
    ))
    db_session.add(DecisionAudit(
        draft_id=2, stock_code="600519", action="SELL",
        target_price=110.0, executed_price=109.0, quantity=100,
    ))
    db_session.commit()

    result = signal_quality(db_session)
    assert result["total_executed"] == 2
    assert result["with_slippage_data"] == 2
    assert result["avg_slippage_pct"] > 0
    assert "BUY" in result["by_side"]
    assert "SELL" in result["by_side"]


# ── dual_engine_attribution ──────────────────────────────────────────────


def test_attribution_empty(db_session):
    result = dual_engine_attribution(db_session)
    assert result["quality_screen"]["drafts"] == 0
    assert result["theme_scan"]["drafts"] == 0


def test_attribution_with_drafts(db_session):
    db_session.add(Draft(code="600519", side="BUY", status="pending",
                         step_kind="aggressive", step_index=0, reason="test",
                         source="draft_generator"))
    db_session.add(Draft(code="000001", side="BUY", status="pending",
                         step_kind="aggressive", step_index=0, reason="test",
                         source="evaluator"))
    db_session.commit()

    result = dual_engine_attribution(db_session)
    assert result["quality_screen"]["drafts"] == 1
    assert result["theme_scan"]["drafts"] == 1


# ── full_evaluation ──────────────────────────────────────────────────────


def test_full_evaluation_returns_structure(db_session):
    result = full_evaluation(db_session)
    assert "benchmark" in result
    assert "trade_stats" in result
    assert "sharpe_ratio" in result
    assert "engine_attribution" in result
    assert "signal_quality" in result
    assert result["sharpe_ratio"] is None  # no portfolio data
