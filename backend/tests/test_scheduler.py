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
