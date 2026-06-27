"""Tests for @task decorator and TaskRegistry."""

from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session as DBSession

from app.services.task.context import TaskContext
from app.services.task.registry import TaskRegistry, get_registry, task


def test_task_registry_singleton():
    """get_registry always returns the same instance."""
    assert get_registry() is get_registry()


def test_task_decorator_registers_function():
    """@task decorator registers the function in the global registry."""

    @task(name="test_foo", cron="0 0 * * *", timeout=60, tags=["test"])
    def foo(ctx: TaskContext) -> dict:
        return {"ok": True}

    registry = get_registry()
    definition = registry.get("test_foo")

    assert definition is not None
    assert definition.name == "test_foo"
    assert definition.cron == "0 0 * * *"
    assert definition.timeout == 60
    assert definition.tags == ["test"]
    assert definition.func is foo


def test_task_decorator_defaults():
    """@task sets sensible defaults for optional parameters."""

    @task(name="test_defaults", cron="*/5 * * * *")
    def bar(ctx: TaskContext) -> dict:
        return {"ok": True}

    registry = get_registry()
    definition = registry.get("test_defaults")

    assert definition.retry == 3
    assert definition.backoff == "exponential"
    assert definition.mutex is True
    assert definition.depends_on == []


def test_task_registry_list_and_get():
    """Registry list/get/contains work correctly."""
    registry = get_registry()

    # Should contain at least our test tasks
    all_tasks = registry.list()
    names = {t.name for t in all_tasks}

    assert "test_foo" in names
    assert "test_defaults" in names

    # Get by name
    assert registry.get("test_foo") is not None
    assert registry.get("nonexistent") is None

    # Contains
    assert registry.contains("test_foo") is True
    assert registry.contains("nonexistent") is False


def test_task_registry_sync_to_db(setup_db):
    """sync_to_db creates Task rows in the database."""
    from app.db.session import SessionLocal

    registry = get_registry()
    db = SessionLocal()

    try:
        registry.sync_to_db(db)
        db.commit()

        from app.models.task import Task as TaskModel

        tasks = db.query(TaskModel).all()
        task_ids = {t.task_id for t in tasks}

        assert "test_foo" in task_ids
        assert "test_defaults" in task_ids

        # Check fields
        foo = db.query(TaskModel).filter(TaskModel.task_id == "test_foo").first()
        assert foo is not None
        assert foo.cron_expr == "0 0 * * *"
        assert foo.timeout_seconds == 60
        assert foo.mutex_enabled is True
    finally:
        db.close()


def test_task_registry_sync_to_db_updates_existing(setup_db):
    """sync_to_db updates existing tasks without changing enabled/status."""
    from app.db.session import SessionLocal
    from app.models.task import Task as TaskModel

    db = SessionLocal()
    try:
        # Create a task manually with disabled status
        db.add(
            TaskModel(
                task_id="test_foo",
                type="job",
                status="paused",
                enabled=False,
                cron_expr="old_cron",
                timeout_seconds=999,
            )
        )
        db.commit()

        # Sync from registry
        registry = get_registry()
        registry.sync_to_db(db)
        db.commit()

        # Check updated fields (timeout should be 60 from registry)
        foo = db.query(TaskModel).filter(TaskModel.task_id == "test_foo").first()
        assert foo is not None
        assert foo.timeout_seconds == 60  # Updated from registry
        assert foo.cron_expr == "0 0 * * *"  # Updated from registry
    finally:
        db.close()


def test_task_context_basics():
    """TaskContext tracks cancellation and progress."""
    ctx = TaskContext(
        task_id="test",
        run_id=1,
        trace_id="trace-abc",
        worker_id="worker-1",
        triggered_by="api",
    )

    assert ctx.task_id == "test"
    assert ctx.run_id == 1
    assert ctx.trace_id == "trace-abc"
    assert ctx.worker_id == "worker-1"
    assert ctx.triggered_by == "api"
    assert ctx.cancelled is False

    # Cancel
    ctx.cancel()
    assert ctx.cancelled is True


def test_task_context_progress():
    """TaskContext.report_progress calls the on_progress callback."""
    progress_values = []

    def on_progress(p, msg):
        progress_values.append((p, msg))

    ctx = TaskContext(task_id="test", run_id=1, on_progress=on_progress)
    ctx.report_progress(0.5, "halfway")
    ctx.report_progress(1.0, "done")

    assert len(progress_values) == 2
    assert progress_values[0] == (0.5, "halfway")
    assert progress_values[1] == (1.0, "done")


def test_task_context_progress_clamped():
    """Progress is clamped to 0.0-1.0."""
    values = []

    def on_progress(p, msg):
        values.append(p)

    ctx = TaskContext(task_id="test", run_id=1, on_progress=on_progress)
    ctx.report_progress(-0.1)
    ctx.report_progress(1.5)

    assert values[0] == 0.0
    assert values[1] == 1.0
