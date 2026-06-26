"""Tests for the scheduler module — job registration + manual triggers."""

import pytest

from app import scheduler as sched_module
from app.core.datetime_utils import now


def test_job_registry_has_expected_jobs():
    # v2: v1 jobs (cycle_assessment / thesis_evaluation / plan_evaluation /
    # rebalancing / business_pattern / research_* …) dropped; v2 LLM pipeline
    # jobs (deep_research / quality_screen / thesis_tracker) added.
    assert set(sched_module.JOB_REGISTRY.keys()) == {
        "daily_universe_bootstrap",
        "daily_base_sync",
        "daily_snapshot",
        "alert_evaluation",
        "daily_kline_sync",
        "daily_prev_close_sync",
        "monthly_dividend_sync",
        "quarterly_financials_refresh",
        "quarterly_shareholders_refresh",
        "weekly_dividend_sync",
        "daily_corp_action_apply",
        "intraday_price_poll",
        "pipeline_stale_sweep",
        "daily_draft_generation",
        "daily_sell_trigger",
        "daily_index_sync",
        "v2_deep_research_weekly",
        "v2_quality_screen_weekly",
        "v2_thesis_tracker_weekly",
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


# (v1 thesis_evaluation job tests removed — thesis_monitor_service dropped in v2;
#  v2 uses thesis_tracker_pipeline via v2_thesis_tracker_weekly job)


# ── F14 (2026-06-18): cron day_of_week translation ────────────────────────


def test_translate_dow_field_basic():
    """crontab dow (0=Sun..6=Sat) → APScheduler names (mon/tue/.../sun)."""
    from app.services.scheduler_config_service import _translate_dow_field
    assert _translate_dow_field("1-5") == "mon-fri"
    assert _translate_dow_field("0,6") == "sun,sat"
    assert _translate_dow_field("*") == "*"
    assert _translate_dow_field("*/5") == "*/5"
    assert _translate_dow_field("1,3,5") == "mon,wed,fri"
    assert _translate_dow_field("0-4") == "sun-thu"
    assert _translate_dow_field("7") == "sun"  # crontab 7 = Sunday
    assert _translate_dow_field("2-6") == "tue-sat"


def test_cron_to_trigger_mon_fri_fires_on_monday():
    """F14: '1-5' must mean Mon-Fri (crontab standard), not Tue-Sat."""
    from datetime import datetime
    from app.services.scheduler_config_service import cron_to_trigger

    # Monday 2026-06-15 09:00 UTC, before cron fire time
    monday_9am = datetime(2026, 6, 15, 9, 0, 0)
    trigger = cron_to_trigger("45 17 * * 1-5")
    nxt = trigger.get_next_fire_time(None, monday_9am)
    # Should fire SAME Monday, not Tuesday
    assert nxt is not None
    nxt_utc = nxt.astimezone(__import__("pytz").timezone("UTC"))
    nxt_sh = nxt.astimezone(__import__("pytz").timezone("Asia/Shanghai"))
    assert nxt_sh.weekday() == 0, f"Expected Monday (0), got weekday={nxt_sh.weekday()}"
    assert nxt_sh.day == 15, f"Expected same Monday 2026-06-15, got day={nxt_sh.day}"


def test_cron_to_trigger_skips_saturday():
    """F14: '1-5' must skip Saturday (crontab standard), not fire on it."""
    from datetime import datetime
    import pytz
    from app.services.scheduler_config_service import cron_to_trigger

    # Saturday 2026-06-13 09:00 UTC
    saturday_9am = datetime(2026, 6, 13, 9, 0, 0)
    trigger = cron_to_trigger("45 17 * * 1-5")
    nxt = trigger.get_next_fire_time(None, saturday_9am)
    assert nxt is not None
    nxt_sh = nxt.astimezone(pytz.timezone("Asia/Shanghai"))
    # Saturday=5, Sunday=6, Monday=0 — should jump to Monday
    assert nxt_sh.weekday() == 0, f"Expected Monday (0), got weekday={nxt_sh.weekday()} (was Saturday=5 before fix)"


def test_cron_to_trigger_sunday_weekend_works():
    """F14: explicit '0,6' (Sun+Sat) should still work correctly."""
    from datetime import datetime
    import pytz
    from app.services.scheduler_config_service import cron_to_trigger

    friday_9am = datetime(2026, 6, 12, 9, 0, 0)  # Friday before weekend
    trigger = cron_to_trigger("0 9 * * 0,6")
    nxt = trigger.get_next_fire_time(None, friday_9am)
    nxt_sh = nxt.astimezone(pytz.timezone("Asia/Shanghai"))
    # Next Saturday (day=13, weekday=5)
    assert nxt_sh.weekday() == 5, f"Expected Saturday (5), got {nxt_sh.weekday()}"


# ── F15 (2026-06-18): pipeline stale sweep ────────────────────────────────


def test_recover_stale_runs_marks_old_running_as_failed(db_session):
    """F15: stale pipeline run (status=running, old created_at) → failed."""
    from datetime import datetime, timedelta, timezone
    from app.models.pipeline import PipelineRun
    from app.services.pipelines.base import PipelineStatus
    from app.services.pipelines.manager import PipelineManager

    old_time = now() - timedelta(hours=24)
    run = PipelineRun(
        id="test-stale-run-1",
        pipeline_type="dividends",
        status=PipelineStatus.RUNNING.value,
        config="{}",
        total_items=100,
        completed_items=0,
        failed_items=0,
        started_at=old_time,
        created_at=old_time,
    )
    db_session.add(run)
    db_session.flush()

    recovered = PipelineManager.recover_stale_runs(db_session)
    assert recovered == 1
    db_session.refresh(run)
    assert run.status == PipelineStatus.FAILED.value
    assert run.finished_at is not None


def test_recover_stale_runs_keeps_recent_running(db_session):
    """F15: recent running pipeline (< 10 min old) should NOT be recovered."""
    from datetime import timedelta
    from app.core.datetime_utils import now
    from app.models.pipeline import PipelineRun
    from app.services.pipelines.base import PipelineStatus
    from app.services.pipelines.manager import PipelineManager

    fresh_time = now() - timedelta(minutes=2)
    run = PipelineRun(
        id="test-fresh-run-1",
        pipeline_type="valuations",
        status=PipelineStatus.RUNNING.value,
        config="{}",
        total_items=100,
        completed_items=10,
        failed_items=0,
        started_at=fresh_time,
        created_at=fresh_time,
    )
    db_session.add(run)
    db_session.flush()

    recovered = PipelineManager.recover_stale_runs(db_session)
    assert recovered == 0
    db_session.refresh(run)
    assert run.status == PipelineStatus.RUNNING.value


def test_pipeline_stale_sweep_job_recovers_stuck(db_session, monkeypatch):
    """F15: scheduler sweep job should mark stuck runs as failed.

    L5 fix (2026-06-19): threshold raised to 6h/8h. Fixture must use > 8h
    old timestamp to trigger sweep's hard_threshold path.
    """
    from datetime import timedelta
    from app.core.datetime_utils import now
    from app.models.pipeline import PipelineRun
    from app.services.pipelines.base import PipelineStatus

    # 10 hours old, no updated_at refresh (stuck thread, > 8h hard_threshold)
    old_time = now() - timedelta(hours=10)
    run = PipelineRun(
        id="test-sweep-target",
        pipeline_type="dividends",
        status=PipelineStatus.RUNNING.value,
        config="{}",
        total_items=100,
        completed_items=0,
        failed_items=0,
        started_at=old_time,
        created_at=old_time,
        updated_at=old_time,  # not refreshed in 1h → stuck
    )
    db_session.add(run)
    db_session.flush()

    # Patch SessionLocal so the job uses our test session
    import app.scheduler as sched_module
    from contextlib import contextmanager

    @contextmanager
    def fake_session_local():
        yield db_session

    monkeypatch.setattr(sched_module, "SessionLocal", fake_session_local)

    result = sched_module.pipeline_stale_sweep_job()
    assert result["recovered"] >= 1
    db_session.refresh(run)
    assert run.status == PipelineStatus.FAILED.value


# (v1 F23 research_stale_sweep tests removed — ResearchRun/research_stale_sweep_job
#  dropped in v2; v2 uses pipeline_stale_sweep for the LLM pipeline runs)
