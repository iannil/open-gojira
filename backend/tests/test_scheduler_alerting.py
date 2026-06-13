"""Test scheduler jobs emit system_alert on failure + Pipeline freshness tracking.

S3.5 wires S3.1-S3.4 defense layers into the runtime:

- with_alerting(job_id) decorator emits critical system_alert on exception
- record_pipeline_completion(db, category, success, count, error) updates
  data_freshness after each Pipeline run
- plan_runner.run_plan asserts data freshness on entry (stocks + valuation,
  max_age=48h to tolerate weekend skip)
"""
from datetime import datetime, timedelta

import pytest

from app.services import scheduler_alerting
from app.services.data_freshness_service import (
    DataStaleError,
    get_freshness_report,
)
from app.services.system_alert_service import list_unresolved


@pytest.fixture(autouse=True)
def _use_test_session(monkeypatch):
    """Point scheduler_alerting at the test in-memory engine.

    The decorator opens its own short-lived session via ``SessionLocal`` —
    by default that points at the real DB engine, which would hide alerts
    from the test assertions. Patch it to the test engine so alerts land
    where the ``db_session`` fixture can see them.
    """
    from tests.conftest import TestSessionLocal
    monkeypatch.setattr(scheduler_alerting, "SessionLocal", TestSessionLocal)
    scheduler_alerting.reset_dedup_state()
    yield
    scheduler_alerting.reset_dedup_state()


# ── with_alerting decorator ────────────────────────────────────────────────


def test_scheduler_job_failure_emits_critical_alert(db_session):
    """When a scheduled job raises, system_alert should be created."""
    from app.services.scheduler_alerting import with_alerting

    @with_alerting(job_id="test_job_123")
    def failing_job():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):  # exception propagates
        failing_job()

    alerts = list_unresolved(db_session, category="scheduler")
    assert any("test_job_123" in a.message for a in alerts)
    assert any(a.severity == "critical" for a in alerts)


def test_scheduler_job_success_no_alert(db_session):
    """Successful job execution should not emit any alert."""
    from app.services.scheduler_alerting import with_alerting

    @with_alerting(job_id="test_job_ok")
    def ok_job():
        return 42

    result = ok_job()
    assert result == 42

    alerts = list_unresolved(db_session, category="scheduler")
    assert not any("test_job_ok" in a.message for a in alerts)


def test_scheduler_alerting_idempotent_within_short_window(db_session):
    """Repeated failures of same job shouldn't spam 100s of alerts.

    Dedup window (10 minutes) limits the alert rate so a chronically failing
    job doesn't drown the alert feed.
    """
    from app.services.scheduler_alerting import with_alerting

    @with_alerting(job_id="spam_job")
    def failing():
        raise ValueError("x")

    for _ in range(10):
        with pytest.raises(ValueError):
            failing()

    alerts = [
        a for a in list_unresolved(db_session, category="scheduler")
        if "spam_job" in a.message
    ]
    # 至少 1 个,最多 5 个(可配置策略)
    assert 1 <= len(alerts) <= 5


# ── record_pipeline_completion ────────────────────────────────────────────


def test_pipeline_records_freshness_on_success(db_session):
    """Pipeline completion should update data_freshness."""
    from app.services.scheduler_alerting import record_pipeline_completion

    record_pipeline_completion(
        db_session, "valuation", success=True, record_count=5000,
    )
    db_session.commit()

    report = get_freshness_report(db_session)
    assert "valuation" in report
    assert report["valuation"]["record_count"] == 5000
    assert report["valuation"]["last_error"] is None


def test_pipeline_records_failure(db_session):
    """Pipeline failure should set last_error on data_freshness row."""
    from app.services.scheduler_alerting import record_pipeline_completion

    record_pipeline_completion(
        db_session, "kline", success=False, error="timeout",
    )
    db_session.commit()

    report = get_freshness_report(db_session)
    assert report["kline"]["last_error"] == "timeout"


# ── plan_runner freshness gate ─────────────────────────────────────────────


def _make_minimal_plan(db_session) -> "object":
    """Build a minimal active Plan with custom scope (no strategies needed
    to trigger the freshness gate — it runs before scope resolution)."""
    import json as _json
    from app.models.plan import Plan

    plan = Plan(
        name="freshness-gate-test",
        slug="freshness_gate_test",
        description="",
        status="active",
        strategy_composition_json=_json.dumps({"strategy_ids": [], "logic": "AND"}),
        scan_scope_json=_json.dumps({"type": "custom", "values": ["600519"]}),
        trading_rules_json=None,
        is_builtin=False,
    )
    db_session.add(plan)
    db_session.flush()
    return plan


def test_plan_runner_checks_freshness_before_evaluating(db_session):
    """If data is stale, plan_runner should refuse to run."""
    from app.models.data_freshness import DataFreshness
    from app.services import plan_runner

    # Insert stale valuation row (72h old, beyond the 48h gate).
    # NOTE: stocks also needs a row or it raises first — both are gated.
    from datetime import timezone
    stale = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=72)
    db_session.add(DataFreshness(
        category="stocks",
        last_synced_at=stale, last_success_at=stale,
        last_record_count=100,
    ))
    db_session.add(DataFreshness(
        category="valuation",
        last_synced_at=stale, last_success_at=stale,
        last_record_count=100,
    ))
    db_session.commit()

    plan = _make_minimal_plan(db_session)

    with pytest.raises(DataStaleError):
        plan_runner.run_plan(db_session, plan)
