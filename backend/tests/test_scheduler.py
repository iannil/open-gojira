"""Tests for the scheduler module — job registration + manual triggers."""

import pytest

from app import scheduler as sched_module


def test_job_registry_has_expected_jobs():
    assert set(sched_module.JOB_REGISTRY.keys()) == {
        "daily_universe_bootstrap",
        "daily_base_sync",
        "daily_deep_sync",
        "daily_snapshot",
        "daily_cycle_assessment",
        "alert_evaluation",
        "thesis_evaluation",
        "daily_kline_sync",
        "daily_prev_close_sync",
        "monthly_dividend_sync",
        "quarterly_financials_refresh",
        "quarterly_shareholders_refresh",
        "daily_plan_evaluation",
        "weekly_rebalancing_review",
        "monthly_thesis_variable_sync",
        "weekly_business_pattern_inference",
        "intraday_monitor",
        "weekly_dividend_sync",
        "daily_corp_action_apply",
        "intraday_price_poll",
        "weekly_research_refresh",
    }


def test_run_job_now_unknown_job_raises():
    with pytest.raises(KeyError):
        sched_module.run_job_now("does_not_exist")


def test_extract_pct_handles_both_formats():
    assert sched_module._extract_pct(None) is None
    assert sched_module._extract_pct(0.25) == 25.0
    assert sched_module._extract_pct(45.0) == 45.0
    assert sched_module._extract_pct({"cvpos": 0.10}) == 10.0
    assert sched_module._extract_pct({"cvpos": None}) is None


def test_start_scheduler_disabled_by_default(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "SCHEDULER_ENABLED", False)
    sched_module._scheduler = None
    out = sched_module.start_scheduler()
    assert out is None


def test_thesis_evaluation_job_invokes_both_checks(monkeypatch):
    """v2 Q6'-A2: independent thesis_evaluation_job must call both
    check_held_stocks (legacy thesis_variables_json) and check_claim_variables
    (new research_claim_variables)."""
    from app.services import thesis_monitor_service

    legacy_calls = []
    claim_calls = []

    def fake_legacy(db):
        legacy_calls.append(db)
        return []  # no legacy alerts

    def fake_claim(db):
        from app.services.thesis_monitor_service import ClaimVariableMonitorSummary
        claim_calls.append(db)
        return ClaimVariableMonitorSummary(checked=1, breached=0)

    monkeypatch.setattr(thesis_monitor_service, "check_held_stocks", fake_legacy)
    monkeypatch.setattr(thesis_monitor_service, "check_claim_variables", fake_claim)

    result = sched_module.thesis_evaluation_job()

    assert len(legacy_calls) == 1
    assert len(claim_calls) == 1
    assert result["legacy_alerts"] == 0
    assert result["checked"] == 1
    assert result["breached"] == 0


def test_run_job_now_thesis_evaluation_executes(monkeypatch):
    """run_job_now('thesis_evaluation') must dispatch to thesis_evaluation_job."""
    from app.services import thesis_monitor_service

    monkeypatch.setattr(
        thesis_monitor_service, "check_held_stocks", lambda db: []
    )
    monkeypatch.setattr(
        thesis_monitor_service, "check_claim_variables",
        lambda db: thesis_monitor_service.ClaimVariableMonitorSummary(),
    )

    result = sched_module.run_job_now("thesis_evaluation")
    assert result["job"] == "thesis_evaluation"
    assert "result" in result
    inner = result["result"]
    assert "checked" in inner
    assert "breached" in inner
    assert "legacy_alerts" in inner
