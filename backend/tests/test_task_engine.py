"""Tests for TaskEngine dispatch logic."""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.models.task import Task as TaskModel, TaskRun
from app.services.task.context import TaskContext
from app.services.task.dependency import DependencyChecker
from app.services.task.engine import TaskEngine
from app.services.task.mutex import MutexLock
from app.services.task.registry import TaskDefinition, get_registry
from app.services.task.retry_manager import RetryManager
from app.services.task.timeout_watchdog import TimeoutWatchdog


# ── DependencyChecker ────────────────────────────────────────────────


def test_dependency_checker_no_deps():
    """No dependencies → always satisfied."""
    task = MagicMock(spec=TaskModel)
    task.depends_on = None
    satisfied, reason = DependencyChecker.are_dependencies_satisfied(None, task)  # type: ignore[arg-type]
    assert satisfied is True
    assert reason is None


def test_dependency_checker_parse_depends_on():
    """Parses JSON depends_on correctly."""
    task = MagicMock(spec=TaskModel)
    task.depends_on = '["upstream_a", "upstream_b"]'
    deps = DependencyChecker.get_depends_on(task)
    assert deps == ["upstream_a", "upstream_b"]


def test_dependency_checker_parse_empty():
    """Empty depends_on returns empty list."""
    task = MagicMock(spec=TaskModel)
    task.depends_on = None
    deps = DependencyChecker.get_depends_on(task)
    assert deps == []


# ── MutexLock ────────────────────────────────────────────────────────


def test_mutex_lock_acquire_no_conflict(setup_db):
    """No existing running run → lock acquired."""
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        # Create a queued run
        run = TaskRun(task_id="test_mutex", status="queued")
        db.add(run)
        db.flush()

        assert MutexLock.try_acquire(db, "test_mutex", run.id) is True
    finally:
        db.close()


def test_mutex_lock_acquire_conflict(setup_db):
    """Existing running run for same task → lock not acquired."""
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        # Create a running run (different run_id)
        run1 = TaskRun(task_id="test_mutex", status="running")
        db.add(run1)
        db.flush()

        run2 = TaskRun(task_id="test_mutex", status="queued")
        db.add(run2)
        db.flush()

        assert MutexLock.try_acquire(db, "test_mutex", run2.id) is False
    finally:
        db.close()


# ── RetryManager ─────────────────────────────────────────────────────


def test_retry_parse_config():
    """Parses retry_config JSON correctly."""
    config = RetryManager.parse_config(
        '{"max_retries":5,"backoff":"linear","max_delay_seconds":120}'
    )
    assert config["max_retries"] == 5
    assert config["backoff"] == "linear"
    assert config["max_delay_seconds"] == 120


def test_retry_parse_config_none():
    """None config returns defaults."""
    config = RetryManager.parse_config(None)
    assert config["max_retries"] == 3
    assert config["backoff"] == "exponential"


def test_retry_wait_exponential():
    """Exponential backoff: 2^retry * 10, capped at max_delay."""
    config = {"backoff": "exponential", "max_delay_seconds": 300}
    assert RetryManager.get_wait_seconds(0, config) == 10
    assert RetryManager.get_wait_seconds(1, config) == 20
    assert RetryManager.get_wait_seconds(2, config) == 40
    assert RetryManager.get_wait_seconds(5, config) == 300  # capped


def test_retry_wait_fixed():
    """Fixed backoff always returns 60 (or max_delay)."""
    config = {"backoff": "fixed", "max_delay_seconds": 300}
    assert RetryManager.get_wait_seconds(1, config) == 60
    assert RetryManager.get_wait_seconds(10, config) == 60


def test_retry_wait_none():
    """No backoff returns 0."""
    config = {"backoff": "none", "max_delay_seconds": 300}
    assert RetryManager.get_wait_seconds(1, config) == 0


def test_retry_should_not_retry_permanent():
    """Permanent errors are not retried."""
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        run = TaskRun(
            task_id="test", status="failed",
            retry_count=0, max_retries=3,
            last_error="[PERMANENT] Something bad",
        )
        assert RetryManager.should_retry(db, run) is False
    finally:
        db.close()


# ── TimeoutWatchdog ──────────────────────────────────────────────────


def test_timeout_watchdog_tracks_and_untracks():
    """Watchdog correctly tracks and untracks runs."""
    watchdog = TimeoutWatchdog(check_interval=0.1)
    watchdog.start()

    import time

    watchdog.track(1, time.monotonic(), 999)
    assert watchdog.active_count == 1

    watchdog.untrack(1)
    assert watchdog.active_count == 0

    watchdog.shutdown()


def test_timeout_watchdog_fires_timeout():
    """Watchdog fires on_timeout when a task exceeds its timeout."""
    import time

    timeout_fired = []

    def on_timeout(run_id):
        timeout_fired.append(run_id)

    watchdog = TimeoutWatchdog(check_interval=0.05, on_timeout=on_timeout)
    watchdog.start()

    # Track a run that already timed out
    watchdog.track(42, time.monotonic() - 10, timeout_seconds=1)

    import time as _time
    _time.sleep(0.15)
    watchdog.shutdown()

    assert 42 in timeout_fired


# ── TaskEngine ───────────────────────────────────────────────────────


def test_engine_trigger_task_creates_run(setup_db):
    """trigger_task creates a queued TaskRun."""
    from app.db.session import SessionLocal
    from app.services.task.registry import task, get_registry

    # Register and sync to DB
    @task(name="test_engine_trigger", cron="0 0 * * *", timeout=60)
    def dummy(ctx):
        return {"ok": True}

    registry = get_registry()
    db = SessionLocal()
    try:
        registry.sync_to_db(db)
        db.commit()

        engine = TaskEngine(tick_interval=999)
        run = engine.trigger_task("test_engine_trigger", db, triggered_by="api")
        db.commit()

        assert run.id > 0
        assert run.task_id == "test_engine_trigger"
        assert run.status == "queued"
        assert run.triggered_by == "api"
    finally:
        db.close()


def test_engine_pause_resume(setup_db):
    """pause_task and resume_task toggle a task's enabled flag."""
    from app.db.session import SessionLocal
    from app.models.task import Task as TaskModel

    # Register and sync
    from app.services.task.registry import task as _task
    @_task(name="test_pause_resume", cron="0 0 * * *", timeout=60)
    def dummy(ctx):
        return {"ok": True}

    registry = get_registry()
    db = SessionLocal()
    try:
        registry.sync_to_db(db)
        db.commit()

        engine = TaskEngine(tick_interval=999)

        # Pause
        assert engine.pause_task("test_pause_resume", db) is True
        db.commit()
        t = db.query(TaskModel).filter(TaskModel.task_id == "test_pause_resume").first()
        assert t.enabled is False

        # Resume
        assert engine.resume_task("test_pause_resume", db) is True
        db.commit()
        t = db.query(TaskModel).filter(TaskModel.task_id == "test_pause_resume").first()
        assert t.enabled is True
        assert t.status == "active"
    finally:
        db.close()


def test_engine_cancel_queued_run(setup_db):
    """cancel_task_run can cancel a queued run."""
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        run = TaskRun(task_id="test_cancel", status="queued")
        db.add(run)
        db.flush()

        engine = TaskEngine(tick_interval=999)
        result = engine.cancel_task_run(run.id, db)
        db.commit()

        assert result is True
        updated = db.query(TaskRun).filter(TaskRun.id == run.id).first()
        assert updated.status == "cancelled"
    finally:
        db.close()
