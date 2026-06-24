"""Smoke tests for v2 LLM infrastructure (Phase 1).

Tests:
  - LLMClient imports + factory
  - cost_tracker math
  - prompt_loader loads shared prompts
  - conflict_validator detects mismatches
  - red_line_checker detects consecutive losses
  - LLMClient.end-to-end with mocked Zhipu SDK (no real API call)
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.db.session import SessionLocal
from app.models import LLMCallLog
from app.models.financial import FinancialStatement
from app.models.valuation import ValuationSnapshot
from app.services.llm import cost_tracker, conflict_validator, red_line_checker
from app.services.llm.client import (
    GLMTier,
    LLMClient,
    LLMClientError,
    get_llm_client,
    reset_llm_client,
)
from app.services.llm.prompt_loader import build_system_prompt, load_shared
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def test_glmtier_values():
    """GLM model constants match decision 4."""
    assert GLMTier.HAIKU.value == "glm-4.8"
    assert GLMTier.SONNET.value == "glm-5.1"
    assert GLMTier.OPUS.value == "glm-5.2"


def test_cost_estimates_cheap():
    """Cost tracker computes reasonable USD per call."""
    # 50K input + 5K output on glm-5.1 (default tier)
    cost = cost_tracker.compute_cost_usd("glm-5.1", 50_000, 5_000)
    assert 0 < cost < 0.10, f"expected cheap, got ${cost}"

    # glm-5.2 (Opus equivalent) should be more expensive
    cost_opus = cost_tracker.compute_cost_usd("glm-5.2", 50_000, 5_000)
    assert cost_opus > cost

    # glm-4.8 should be cheapest
    cost_haiku = cost_tracker.compute_cost_usd("glm-4.8", 10_000, 2_000)
    assert cost_haiku < cost


def test_shared_prompts_loaded():
    """All 3 shared prompt files exist and have content."""
    for name in ("system_base", "defense_methodology", "evidence_grading"):
        content = load_shared(name)
        assert len(content) > 200, f"{name}.md too short: {len(content)} chars"


def test_build_system_prompt_assembles_all():
    """Full system prompt includes all 3 shared sections."""
    sp = build_system_prompt("deep_research", "v1")
    assert "Gojira" in sp
    assert "8 红线" in sp or "red line" in sp.lower()
    assert "strong" in sp and "medium" in sp  # evidence grading levels
    assert "---" in sp  # separator between sections


def test_red_line_consecutive_losses_detected(setup_db):
    """check_consecutive_losses flags 3 years of negative net profit."""
    db = SessionLocal()
    try:
        # Setup: 3 annual reports with negative net_profit
        from datetime import date
        for year in (2023, 2024, 2025):
            db.add(FinancialStatement(
                stock_code="600519",
                report_date=date(year, 12, 31),
                report_type="annual",
                revenue=10e8,
                net_profit=-1e8,
                eps_basic=-0.5,
            ))
        db.commit()

        hit = red_line_checker.check_consecutive_losses(db, "600519")
        assert hit is not None
        assert hit.red_line_type == red_line_checker.RED_LINE_CONSECUTIVE_LOSSES
        assert hit.severity == "hard_reject"
        assert hit.evidence["consecutive_years"] == 3
    finally:
        db.close()


def test_red_line_no_false_positive_on_profitable(setup_db):
    """Profitable company does not trigger consecutive_losses."""
    db = SessionLocal()
    try:
        from datetime import date
        for year in (2023, 2024, 2025):
            db.add(FinancialStatement(
                stock_code="600519",
                report_date=date(year, 12, 31),
                report_type="annual",
                revenue=10e8,
                net_profit=1e8,  # positive
                eps_basic=0.5,
            ))
        db.commit()

        hit = red_line_checker.check_consecutive_losses(db, "600519")
        assert hit is None
    finally:
        db.close()


def test_llm_flagged_red_lines_parsed():
    """LLM output's red_line_flags field is parsed correctly."""
    llm_output = {
        "red_line_flags": {
            "management_integrity": {"evidence": "CEO 涉嫌财务造假被调查"},
            "high_pledge": {"evidence": "控股股东质押 65%"},
        }
    }
    hits = red_line_checker.check_llm_flagged_red_lines(llm_output)
    assert len(hits) == 2
    types = {h.red_line_type for h in hits}
    assert "management_integrity" in types
    assert "high_pledge" in types


def test_conflict_validator_detects_pe_mismatch(setup_db):
    """conflict_validator flags PE mismatch > 5%."""
    db = SessionLocal()
    try:
        from datetime import date
        db.add(ValuationSnapshot(
            stock_code="600519",
            date=date(2026, 6, 24),
            pe_ttm=30.0,  # DB says 30
            pb=8.0,
            dividend_yield=0.015,
        ))
        db.commit()

        # LLM says PE is 40 — that's +33% off
        conflicts = conflict_validator.validate_financials(
            db, "600519", {"pe": 40.0}
        )
        assert len(conflicts) == 1
        assert conflicts[0].field == "pe"
        assert conflicts[0].diff_pct > 5.0
        assert conflicts[0].llm_value == 40.0
        assert conflicts[0].db_value == 30.0
    finally:
        db.close()


def test_conflict_validator_tolerates_small_diff(setup_db):
    """conflict_validator does NOT flag mismatches < 5%."""
    db = SessionLocal()
    try:
        from datetime import date
        db.add(ValuationSnapshot(
            stock_code="600519",
            date=date(2026, 6, 24),
            pe_ttm=30.0,
            pb=8.0,
            dividend_yield=0.015,
        ))
        db.commit()

        # LLM says PE 30.5 — that's +1.67% off (within tolerance)
        conflicts = conflict_validator.validate_financials(
            db, "600519", {"pe": 30.5}
        )
        assert len(conflicts) == 0
    finally:
        db.close()


def test_llm_client_factory_requires_api_key():
    """get_llm_client raises if no API key configured."""
    reset_llm_client()
    # Patch settings to remove key
    with patch("app.config.settings.ZHIPU_API_KEY", ""):
        with pytest.raises(LLMClientError, match="ZHIPU_API_KEY"):
            get_llm_client()


def test_llm_client_records_call_log_on_success(setup_db):
    """LLMClient.complete() writes to llm_call_logs after success."""
    # Mock ZhipuAI client
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "analysis"
    mock_response.choices[0].message.tool_calls = [MagicMock()]
    mock_response.choices[0].message.tool_calls[0].function.name = "submit_result"
    mock_response.choices[0].message.tool_calls[0].function.arguments = '{"score": 4.2}'
    mock_response.usage.prompt_tokens = 1000
    mock_response.usage.completion_tokens = 200

    mock_zhipu = MagicMock()
    mock_zhipu.chat.completions.create.return_value = mock_response

    client = LLMClient(api_key="fake-key")
    client._client = mock_zhipu

    # Patch prompt_loader to return minimal prompt (pipeline dir not built yet)
    with patch("app.services.llm.client.build_system_prompt", return_value="sys"):
        db = SessionLocal()
        try:
            response = client.complete(
                user_prompt="analyze 600519",
                pipeline="deep_research",
                model=GLMTier.SONNET,
                response_schema={"type": "object", "properties": {}},
                stock_code="600519",
                db_session=db,
            )
            db.commit()

            assert response.tool_call_args == {"score": 4.2}
            assert response.usage["tokens_in"] == 1000
            assert response.usage["tokens_out"] == 200
            assert response.cost_usd > 0

            # Verify llm_call_logs row written
            log_count = db.query(LLMCallLog).filter(
                LLMCallLog.stock_code == "600519"
            ).count()
            assert log_count == 1

            log = db.query(LLMCallLog).filter(
                LLMCallLog.stock_code == "600519"
            ).first()
            assert log.model == "glm-5.1"
            assert log.success is True
            assert log.tokens_in == 1000
        finally:
            db.close()


def test_llm_client_records_failure_after_retries(setup_db):
    """LLMClient writes failure log after MAX_RETRIES exhausted."""
    mock_zhipu = MagicMock()
    mock_zhipu.chat.completions.create.side_effect = Exception("API down")

    client = LLMClient(api_key="fake-key")
    client._client = mock_zhipu

    # Speed up test: patch backoff to 0
    with patch("app.services.llm.client.build_system_prompt", return_value="sys"), \
         patch("app.services.llm.client.INITIAL_BACKOFF_SEC", 0.001), \
         patch("app.services.llm.client.BACKOFF_MULTIPLIER", 1.0):
        db = SessionLocal()
        try:
            with pytest.raises(LLMClientError, match="failed after 3 attempts"):
                client.complete(
                    user_prompt="x",
                    pipeline="deep_research",
                    model=GLMTier.HAIKU,
                    stock_code="600519",
                    db_session=db,
                )
            db.commit()

            log = db.query(LLMCallLog).filter(
                LLMCallLog.stock_code == "600519"
            ).first()
            assert log is not None
            assert log.success is False
            assert "API down" in (log.error_message or "")
        finally:
            db.close()
