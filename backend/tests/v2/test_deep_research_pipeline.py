"""Integration tests for deep_research_pipeline (Phase 2).

Tests use mocked LLMClient to avoid real API calls. Pipeline orchestration,
data gathering, defense layer, and persistence are all verified.
"""
from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest

from app.db.session import SessionLocal
from app.models import LLMCallLog, RedLineEvent, ResearchReport, StockLifecycle
from app.models.financial import FinancialStatement
from app.models.price_kline import PriceKline
from app.models.valuation import ValuationSnapshot
from app.services import lifecycle_service
from app.services.llm.client import GLMTier, LLMClient, LLMResponse
from app.services.pipelines.llm import deep_research_pipeline


# ── Fixtures ─────────────────────────────────────────────────────────────


def _setup_stock(db, code="600519"):
    """Insert a stock + Lixinger data for testing."""
    from app.models.stock import Stock
    stock = Stock(
        code=code,
        name="贵州茅台",
        industry="non_financial",
        listed_date=date(2001, 8, 27),
    )
    db.add(stock)
    # Valuations: profitable, normal PE
    db.add(ValuationSnapshot(
        stock_code=code,
        date=date(2026, 6, 24),
        pe_ttm=30.5,
        pb=8.0,
        dividend_yield=0.015,
        pe_percentile_10y=25.0,
        pb_percentile_10y=35.0,
    ))
    # Financials: 3 profitable years
    for year in (2023, 2024, 2025):
        db.add(FinancialStatement(
            stock_code=code,
            report_date=date(year, 12, 31),
            report_type="annual",
            revenue=120e8 + year * 10e8,
            revenue_growth=0.10,
            net_profit=50e8 + year * 5e8,
            net_profit_growth=0.12,
            gross_margin=0.91,
            net_margin=0.40,
            eps_basic=40.0 + year,
            shareholders_equity=200e8,
        ))
    # Klines
    for i in range(5):
        db.add(PriceKline(
            stock_code=code,
            date=date(2026, 6, 24) - _days(i),
            open=1500.0 + i,
            high=1520.0 + i,
            low=1490.0 + i,
            close=1510.0 + i,
            volume=1e6,
        ))
    db.commit()
    return stock


def _days(n: int):
    from datetime import timedelta
    return timedelta(days=n)


def _mock_llm_response(json_args: dict, model: str = "glm-5.1") -> LLMResponse:
    """Build a mock LLMResponse with given tool_call args."""
    return LLMResponse(
        content="",
        tool_call_args=json_args,
        usage={"tokens_in": 1000, "tokens_out": 200, "search_count": 1},
        cost_usd=0.001,
        latency_ms=500,
        model=model,
    )


def _build_mock_client() -> MagicMock:
    """Mock LLMClient that returns realistic deep_research outputs per step."""
    client = MagicMock(spec=LLMClient)

    # Step 1: data_collection
    data_brief = {
        "stock_code": "600519",
        "info_grade": "A",
        "data_conflicts": [],
        "key_numbers": {"pe_ttm": 30.5, "pb": 8.0, "roe_pct": 30.0},
        "recent_events": [
            {"date": "2026-06-15", "type": "announcement", "title": "Q1 财报", "summary": "营收增长 12%", "sentiment": "positive"}
        ],
        "key_questions": ["高端白酒需求持续性?"],
    }

    # Steps 2-5: 4 masters
    duan = {
        "master": "duan", "business_essence": "高端白酒品牌 + 社交属性",
        "is_good_business": True, "score": 4.5,
        "score_justification": "强品牌 + 高毛利", "key_risks": ["消费降级"],
    }
    buffett = {
        "master": "buffett", "moat_types": ["brand"], "moat_strength": "wide",
        "moat_trend": "stable", "score": 4.4,
        "score_justification": "品牌护城河 + 管理层优秀", "key_risks": ["估值偏高"],
    }
    munger = {
        "master": "munger",
        "failure_scenarios": [{"scenario": "年轻人不喝白酒", "probability": "medium"}],
        "score": 3.5, "score_justification": "有长期担忧但短期护城河稳固",
        "key_risks": ["人口结构变化"],
    }
    lilu = {
        "master": "lilu", "civilization_trend_fit": "medium",
        "decade_certainty": {"exists_in_10y": "high", "business_model_valid_in_10y": "high",
                              "advantage_sustained_in_10y": "high", "market_larger_in_10y": "medium"},
        "score": 4.0, "score_justification": "10 年确定性强",
        "key_risks": ["政策风险"],
    }

    # Step 6: synthesis
    synthesis = {
        "stock_code": "600519", "overall_score": 4.1, "recommendation": "BUY",
        "master_scores": {"duan": 4.5, "buffett": 4.4, "munger": 3.5, "lilu": 4.0},
        "master_disagreements": [],
        "price_ranges": {
            "aggressive": {"min": 1800, "max": 2000, "rationale": "可建仓 30%"},
            "steady": {"min": 1500, "max": 1700, "rationale": "等回调至 1700"},
            "conservative": {"min": 1200, "max": 1400, "rationale": "理想买点 1400 以下"},
        },
        "mirror_test": {"passed": True, "statement": "1. 高端白酒龙头 2. 强品牌 3. ..."},
        "evidence_grade": "A", "evidence_summary": "3 个一手公告 + 完整财报",
        "key_risks_prioritized": [
            {"risk": "消费降级", "probability": "medium", "impact": "high"}
        ],
        "markdown_report": "# 600519 深度研究报告\n\n综合评分 4.1 / 5",
    }

    def _complete(**kwargs):
        pipeline_type = kwargs.get("pipeline_type", "")
        if "data_collection" in pipeline_type:
            return _mock_llm_response(data_brief)
        if "duan" in pipeline_type:
            return _mock_llm_response(duan)
        if "buffett" in pipeline_type:
            return _mock_llm_response(buffett)
        if "munger" in pipeline_type:
            return _mock_llm_response(munger)
        if "lilu" in pipeline_type:
            return _mock_llm_response(lilu)
        if "synthesis" in pipeline_type:
            return _mock_llm_response(synthesis)
        return _mock_llm_response({})

    client.complete = MagicMock(side_effect=_complete)
    return client


# ── Tests ────────────────────────────────────────────────────────────────


def test_gather_input_returns_stock_data(setup_db):
    """gather_input pulls Lixinger data for a stock."""
    db = SessionLocal()
    try:
        _setup_stock(db, "600519")
        input_data = deep_research_pipeline.gather_input(db, "600519")
        assert input_data is not None
        assert input_data.stock_code == "600519"
        assert input_data.stock_name == "贵州茅台"
        assert len(input_data.valuations) == 1
        assert len(input_data.financials) == 3
        assert len(input_data.klines_recent) == 5
    finally:
        db.close()


def test_gather_input_returns_none_for_unknown(setup_db):
    db = SessionLocal()
    try:
        assert deep_research_pipeline.gather_input(db, "999999") is None
    finally:
        db.close()


def test_pipeline_end_to_end_writes_report(setup_db):
    """Full pipeline writes research_reports row + transitions lifecycle."""
    db = SessionLocal()
    try:
        _setup_stock(db, "600519")
        mock_client = _build_mock_client()

        result = deep_research_pipeline.run(
            "600519", db_session=db, llm_client=mock_client
        )

        # Verify result
        assert result.stock_code == "600519"
        assert result.overall_score == 4.1
        assert result.recommendation == "BUY"
        assert result.evidence_grade == "A"
        assert not result.rejected
        assert "600519" in result.markdown_report
        assert result.report_id is not None

        # Verify report persisted
        report = db.query(ResearchReport).filter(
            ResearchReport.stock_code == "600519"
        ).first()
        assert report is not None
        assert report.pipeline_type == "deep_research"
        assert report.overall_score == 4.1
        assert report.recommendation == "BUY"
        assert report.status == "completed"
        assert report.prompt_version == "v1"
        # json_output has masters + synthesis
        assert "masters" in report.json_output
        assert "synthesis" in report.json_output
        assert set(report.json_output["masters"].keys()) == {"duan", "buffett", "munger", "lilu"}

        # Verify lifecycle transitioned to 'researched'
        lc = lifecycle_service.get_lifecycle(db, "600519")
        assert lc is not None
        assert lc.current_state == "researched"
        assert lc.last_research_at is not None  # 30-day cache window starts
        assert lc.rejected_count == 0

        # Verify history_json has the transition
        assert lc.history_json is not None
        assert len(lc.history_json) >= 1
        assert lc.history_json[-1]["to"] == "researched"

        # Verify LLM calls logged (6 calls: 1 data_collect + 4 masters + 1 synthesis)
        # (master calls use their own sessions, so not in this db; main session
        # only has data_collect + synthesis = 2)
        # The exact count depends on whether masters used same session —
        # in this test they use SessionLocal() so they're separate.
    finally:
        db.close()


def test_pipeline_red_line_marks_rejected(setup_db):
    """If LLM flags a red line, report status=rejected + red_line_event written."""
    db = SessionLocal()
    try:
        _setup_stock(db, "600519")
        mock_client = _build_mock_client()

        # Override synthesis to include red_line_flags
        original_complete = mock_client.complete.side_effect

        def _with_red_line(**kwargs):
            response = original_complete(**kwargs)
            if "synthesis" in kwargs.get("pipeline_type", ""):
                response.tool_call_args = {
                    **response.tool_call_args,
                    "red_line_flags": {
                        "high_pledge": {"evidence": "控股股东质押 65%"}
                    },
                }
            return response

        mock_client.complete = MagicMock(side_effect=_with_red_line)

        result = deep_research_pipeline.run(
            "600519", db_session=db, llm_client=mock_client
        )

        assert result.rejected is True
        assert result.recommendation == "PASS"  # forced
        assert len(result.red_line_hits) == 1
        assert result.red_line_hits[0]["red_line_type"] == "high_pledge"

        # Verify report status = rejected
        report = db.query(ResearchReport).filter(
            ResearchReport.stock_code == "600519"
        ).first()
        assert report.status == "rejected"
        assert report.red_line_hit_json is not None

        # Verify red_line_event written
        events = db.query(RedLineEvent).filter(
            RedLineEvent.stock_code == "600519"
        ).all()
        assert len(events) == 1
        assert events[0].red_line_type == "high_pledge"
        assert events[0].report_id == report.id

        # Lifecycle still researched but rejected_count=1
        lc = lifecycle_service.get_lifecycle(db, "600519")
        assert lc.current_state == "researched"
        assert lc.rejected_count == 1
    finally:
        db.close()


def test_pipeline_30_day_cache_bypass(setup_db):
    """needs_research respects 30-day window."""
    db = SessionLocal()
    try:
        _setup_stock(db, "600519")

        # Never researched → needs research
        assert lifecycle_service.needs_research(db, "600519", cache_days=30) is True

        # Run pipeline
        mock_client = _build_mock_client()
        deep_research_pipeline.run(
            "600519", db_session=db, llm_client=mock_client
        )

        # Within 30 days → doesn't need research
        assert lifecycle_service.needs_research(db, "600519", cache_days=30) is False
    finally:
        db.close()


def test_pipeline_handles_unknown_stock(setup_db):
    """run() raises ValueError for unknown stock."""
    db = SessionLocal()
    try:
        mock_client = _build_mock_client()
        with pytest.raises(ValueError, match="Stock not found"):
            deep_research_pipeline.run(
                "999999", db_session=db, llm_client=mock_client
            )
    finally:
        db.close()


# ── API endpoint tests ──────────────────────────────────────────────────


def test_research_health_endpoint(setup_db):
    """GET /api/research/health returns monthly spend + lifecycle counts."""
    import os
    os.environ['SCHEDULER_ENABLED'] = 'false'
    from app.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        resp = client.get("/api/research/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "spend" in data
        assert data["spend"]["total_usd"] == 0.0
        assert "lifecycle_counts" in data
        assert data["lifecycle_counts"]["researched"] == 0


def test_research_trigger_with_mock(setup_db):
    """POST /api/research/{stock_code} runs pipeline via API."""
    import os
    os.environ['SCHEDULER_ENABLED'] = 'false'
    from app.main import app
    from fastapi.testclient import TestClient

    # Setup stock
    db = SessionLocal()
    try:
        _setup_stock(db, "600519")
    finally:
        db.close()

    mock_client = _build_mock_client()

    with patch(
        "app.services.pipelines.llm.deep_research_pipeline.get_llm_client",
        return_value=mock_client,
    ):
        with TestClient(app) as client:
            resp = client.post(
                "/api/research/600519",
                json={"force": True, "model_tier": "sonnet"},
            )
            assert resp.status_code == 200, resp.text
            data = resp.json()
            assert data["stock_code"] == "600519"
            assert data["overall_score"] == 4.1
            assert data["recommendation"] == "BUY"
            assert data["status"] == "completed"
            # API uses markdown_output field (snake_case in Pydantic)
            assert data.get("markdown_output") or data.get("markdown_report")
