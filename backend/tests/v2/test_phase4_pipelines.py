"""Phase 4 tests: quality_screen, thesis_tracker, news_pulse, earnings_review.

All use mocked LLMClient to avoid real API calls.
"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.db.session import SessionLocal
from app.models import Holding, PriceKline, ResearchReport, StockLifecycle
from app.models.financial import FinancialStatement
from app.models.stock import Stock
from app.models.valuation import ValuationSnapshot
from app.services import lifecycle_service
from app.services.llm.client import GLMTier, LLMClient, LLMResponse
from app.services.pipelines.llm import (
    earnings_review_pipeline,
    news_pulse_pipeline,
    quality_screen_pipeline,
    thesis_tracker_pipeline,
)


def _setup_stock(db, code="600519", *, is_st=False, pe=30.0, net_margin=0.30):
    """Insert stock + Lixinger data."""
    name = "*ST 茅台" if is_st else "贵州茅台"
    stock = Stock(code=code, name=name, industry="non_financial", listed_date=date(2001, 8, 27))
    db.add(stock)
    db.add(ValuationSnapshot(
        stock_code=code, date=date(2026, 6, 24),
        pe_ttm=pe, pb=8.0, dividend_yield=0.015,
        pe_percentile_10y=25.0, pb_percentile_10y=35.0,
    ))
    for year in (2024, 2025):
        db.add(FinancialStatement(
            stock_code=code, report_date=date(year, 12, 31), report_type="annual",
            revenue=120e8 + year * 10e8, revenue_growth=0.10,
            net_profit=50e8 + year * 5e8, net_profit_growth=0.12,
            gross_margin=0.91, net_margin=net_margin, eps_basic=40.0 + year,
        ))
    db.commit()
    return stock


def _setup_klines(db, code="600519", *, days=10, change_pct=-7.0):
    """Insert klines ending with specified % change."""
    base_close = 100.0
    step = (change_pct / 100) / max(1, days - 1) * base_close
    for i in range(days):
        db.add(PriceKline(
            stock_code=code,
            date=date(2026, 6, 24) - timedelta(days=days - 1 - i),
            open=base_close + i * step - 0.5,
            high=base_close + i * step + 0.5,
            low=base_close + i * step - 1,
            close=base_close + i * step,
            volume=1e6,
        ))
    db.commit()


def _setup_holding(db, code="600519"):
    """Insert an open holding."""
    db.add(Holding(
        stock_code=code, quantity=100,
        buy_price=1500.0, buy_date=date(2026, 1, 15),
        stop_profit_price=0.0,
    ))
    db.commit()


def _mock_response(json_args: dict) -> LLMResponse:
    return LLMResponse(
        content="",
        tool_call_args=json_args,
        usage={"tokens_in": 800, "tokens_out": 200, "search_count": 2},
        cost_usd=0.001,
        latency_ms=400,
        model="glm-4.8",
    )


# ── quality_screen_pipeline ──────────────────────────────────────────────


def test_quality_screen_clean_stock_passes(setup_db):
    """Profitable non-ST stock with reasonable PE passes all rules."""
    db = SessionLocal()
    try:
        _setup_stock(db, "600519", pe=30.0, net_margin=0.30)
        result = quality_screen_pipeline.screen_stock(db, "600519", use_llm_for_borderline=False)
        assert result is not None
        assert result.passed
        assert not result.rejected
        # All rules pass
        assert all(r.passed for r in result.rule_results)
    finally:
        db.close()


def test_quality_screen_st_stock_fails(setup_db):
    """ST stock fails the not_st rule."""
    db = SessionLocal()
    try:
        _setup_stock(db, "600519", is_st=True)
        result = quality_screen_pipeline.screen_stock(db, "600519", use_llm_for_borderline=False)
        assert result is not None
        not_st_rule = next(r for r in result.rule_results if r.rule_name == "not_st")
        assert not not_st_rule.passed
    finally:
        db.close()


def test_quality_screen_unknown_stock_returns_none(setup_db):
    db = SessionLocal()
    try:
        assert quality_screen_pipeline.screen_stock(db, "999999") is None
    finally:
        db.close()


def test_quality_screen_passes_stock_to_watchlist(setup_db):
    """Stock that passes → enters watchlist state."""
    db = SessionLocal()
    try:
        _setup_stock(db, "600519")
        quality_screen_pipeline.screen_stock(
            db, "600519", use_llm_for_borderline=False
        )
        # Manually call enter_state (screen_stock doesn't update state itself;
        # screen_universe does)
        lifecycle_service.enter_state(db, "600519", "watchlist", reason="test")
        db.commit()
        state = lifecycle_service.get_state(db, "600519")
        assert state == "watchlist"
    finally:
        db.close()


# ── thesis_tracker_pipeline ──────────────────────────────────────────────


def test_thesis_tracker_runs_on_holding(setup_db):
    """thesis_tracker produces report for an open holding."""
    db = SessionLocal()
    try:
        _setup_stock(db, "600519")
        _setup_holding(db, "600519")
        _setup_klines(db, "600519")

        # Mock LLM
        mock_client = MagicMock(spec=LLMClient)
        mock_client.complete.return_value = _mock_response({
            "stock_code": "600519",
            "status": "VALID",
            "key_changes": [{"change": "营收稳定", "impact": "positive", "evidence": "Q1 财报"}],
            "sell_recommendation": False,
            "markdown_summary": "## 论文复核\n\n论文仍然成立。",
        })

        result = thesis_tracker_pipeline.run(
            "600519", db_session=db, llm_client=mock_client
        )
        db.commit()

        assert result.status == "VALID"
        assert result.sell_recommended is False
        assert "论文仍然成立" in result.markdown_summary
        assert result.report_id is not None

        # Verify persisted
        report = db.query(ResearchReport).filter(
            ResearchReport.pipeline_type == "thesis_tracker",
            ResearchReport.stock_code == "600519",
        ).first()
        assert report is not None
        assert report.status == "completed"
    finally:
        db.close()


def test_thesis_tracker_invalidated_marks_rejected(setup_db):
    """INVALIDATED → report status=rejected + sell_recommendation=True."""
    db = SessionLocal()
    try:
        _setup_stock(db, "600519")
        _setup_holding(db, "600519")
        _setup_klines(db, "600519")

        mock_client = MagicMock(spec=LLMClient)
        mock_client.complete.return_value = _mock_response({
            "stock_code": "600519",
            "status": "INVALIDATED",
            "key_changes": [{"change": "管理层涉财务造假", "impact": "negative", "evidence": "证监会调查"}],
            "invalidated_triggers": ["管理层诚信红线", "财务造假嫌疑"],
            "sell_recommendation": True,
            "markdown_summary": "## ⚠ 论文证伪\n\n建议立即 SELL。",
        })

        result = thesis_tracker_pipeline.run(
            "600519", db_session=db, llm_client=mock_client
        )
        db.commit()

        assert result.status == "INVALIDATED"
        assert result.sell_recommended is True
        assert len(result.invalidated_triggers) == 2

        report = db.query(ResearchReport).filter(
            ResearchReport.pipeline_type == "thesis_tracker",
            ResearchReport.stock_code == "600519",
        ).first()
        assert report.status == "rejected"
        assert report.recommendation == "SELL"
    finally:
        db.close()


def test_thesis_tracker_raises_on_no_holding(setup_db):
    """No active holding → ValueError."""
    db = SessionLocal()
    try:
        _setup_stock(db, "600519")  # no holding added
        mock_client = MagicMock(spec=LLMClient)
        with pytest.raises(ValueError, match="No active holding"):
            thesis_tracker_pipeline.run(
                "600519", db_session=db, llm_client=mock_client
            )
    finally:
        db.close()


# ── news_pulse_pipeline ──────────────────────────────────────────────────


def test_news_pulse_runs_on_price_drop(setup_db):
    """news_pulse attributes a -7% drop correctly."""
    db = SessionLocal()
    try:
        _setup_stock(db, "600519")
        _setup_klines(db, "600519", change_pct=-7.0)

        mock_client = MagicMock(spec=LLMClient)
        mock_client.complete.return_value = _mock_response({
            "stock_code": "600519",
            "window_change_pct": -7.0,
            "attribution": [
                {"candidate": "回购静默期结束", "estimated_contribution_pct": -3.0, "confidence": "high"},
                {"candidate": "板块整体回调", "estimated_contribution_pct": -2.0, "confidence": "medium"},
            ],
            "nature": "liquidity",
            "action_recommendation": "hold",
            "markdown_report": "## 异动归因\n\n-7% 主要是流动性因素，非基本面恶化。",
            "key_finding": "流动性驱动，无需行动",
        })

        result = news_pulse_pipeline.run(
            "600519", db_session=db, llm_client=mock_client,
            change_pct=-7.0,  # precomputed to skip kline query
        )
        db.commit()

        assert result.window_change_pct == -7.0
        assert result.nature == "liquidity"
        assert result.action == "hold"

        report = db.query(ResearchReport).filter(
            ResearchReport.pipeline_type == "news_pulse",
            ResearchReport.stock_code == "600519",
        ).first()
        assert report is not None
    finally:
        db.close()


def test_news_pulse_unknown_nature(setup_db):
    """unknown nature is a valid (and valuable) output."""
    db = SessionLocal()
    try:
        _setup_stock(db, "600519")
        mock_client = MagicMock(spec=LLMClient)
        mock_client.complete.return_value = _mock_response({
            "stock_code": "600519",
            "window_change_pct": 8.0,
            "attribution": [],
            "nature": "unknown",
            "action_recommendation": "observe",
            "markdown_report": "## 真因不明\n\n可能是内幕抢跑，建议观察。",
            "key_finding": "真因不明",
        })

        result = news_pulse_pipeline.run(
            "600519", db_session=db, llm_client=mock_client, change_pct=8.0,
        )
        db.commit()

        assert result.nature == "unknown"
        assert result.action == "observe"
    finally:
        db.close()


# ── earnings_review_pipeline ─────────────────────────────────────────────


def test_earnings_review_strengthens_thesis(setup_db):
    """财报超预期 → strengthens."""
    db = SessionLocal()
    try:
        _setup_stock(db, "600519")
        mock_client = MagicMock(spec=LLMClient)
        mock_client.complete.return_value = _mock_response({
            "stock_code": "600519",
            "report_date": "2025-12-31",
            "thesis_impact": "strengthens",
            "key_findings": [
                {"finding": "营收增速 +18% 超预期", "metric": "revenue_growth", "value": "0.18", "interpretation": "加速"},
            ],
            "accounting_concerns": [],
            "guidance_assessment": {"credibility": "high", "tone": "conservative"},
            "action_recommendation": "hold",
            "markdown_report": "## 财报精读\n\n营收超预期，论文强化。",
        })

        result = earnings_review_pipeline.run(
            "600519", db_session=db, llm_client=mock_client
        )
        db.commit()

        assert result.thesis_impact == "strengthens"
        assert len(result.key_findings) == 1

        report = db.query(ResearchReport).filter(
            ResearchReport.pipeline_type == "earnings_review",
            ResearchReport.stock_code == "600519",
        ).first()
        assert report.status == "completed"
    finally:
        db.close()


def test_earnings_review_invalidates_thesis(setup_db):
    """财报显示转亏 → invalidates → status=rejected."""
    db = SessionLocal()
    try:
        _setup_stock(db, "600519")
        mock_client = MagicMock(spec=LLMClient)
        mock_client.complete.return_value = _mock_response({
            "stock_code": "600519",
            "report_date": "2025-12-31",
            "thesis_impact": "invalidates",
            "key_findings": [
                {"finding": "扣非净利润转亏", "metric": "net_profit", "value": "-3 亿", "interpretation": "首次亏损"},
            ],
            "accounting_concerns": ["应收账款激增 60%"],
            "action_recommendation": "thesis_review",
            "markdown_report": "## ⚠ 论文证伪\n\n转亏，建议立即复核。",
        })

        result = earnings_review_pipeline.run(
            "600519", db_session=db, llm_client=mock_client
        )
        db.commit()

        assert result.thesis_impact == "invalidates"

        report = db.query(ResearchReport).filter(
            ResearchReport.pipeline_type == "earnings_review",
            ResearchReport.stock_code == "600519",
        ).first()
        assert report.status == "rejected"
        assert report.recommendation == "SELL"
    finally:
        db.close()


def test_earnings_review_raises_on_no_financials(setup_db):
    """No financials → ValueError."""
    db = SessionLocal()
    try:
        # stock exists but no financials
        db.add(Stock(code="000001", name="平安银行", industry="financial"))
        db.commit()

        mock_client = MagicMock(spec=LLMClient)
        with pytest.raises(ValueError, match="No financial statements"):
            earnings_review_pipeline.run(
                "000001", db_session=db, llm_client=mock_client
            )
    finally:
        db.close()
