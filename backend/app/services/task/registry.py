"""TaskRegistry — central registry for @task-decorated functions."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session as DBSession

from app.models.task import Task as TaskModel
from app.services.task.context import TaskContext

# Type alias for a task executor function
TaskFunc = Callable[[TaskContext], dict[str, Any]]


class TaskDefinition:
    """Immutable descriptor for a registered task."""

    def __init__(
        self,
        name: str,
        func: TaskFunc,
        type_: str = "job",
        trigger_type: str = "cron",
        cron: str | None = None,
        event_source: str | None = None,
        depends_on: list[str] | None = None,
        retry: int = 3,
        backoff: str = "exponential",
        max_delay: int = 300,
        timeout: int = 600,
        mutex: bool = True,
        tags: list[str] | None = None,
        description: str | None = None,
    ):
        self.name = name
        self.func = func
        self.type = type_
        self.trigger_type = trigger_type
        self.cron = cron
        self.event_source = event_source
        self.depends_on = depends_on or []
        self.retry = retry
        self.backoff = backoff
        self.max_delay = max_delay
        self.timeout = timeout
        self.mutex = mutex
        self.tags = tags or []
        self.description = description


class TaskRegistry:
    """Central registry for all @task-decorated functions.

    Thread-safe. Scans app.tasks packages on initialization.
    Supports DB sync to keep the `tasks` table in sync with registered code.
    """

    def __init__(self):
        self._definitions: dict[str, TaskDefinition] = {}
        self._lock = threading.Lock()

    # ── Registration ────────────────────────────────────────────────────

    def register(self, definition: TaskDefinition) -> None:
        """Register a TaskDefinition (thread-safe)."""
        with self._lock:
            self._definitions[definition.name] = definition

    def get(self, name: str) -> TaskDefinition | None:
        """Look up a TaskDefinition by name."""
        return self._definitions.get(name)

    def list(self) -> list[TaskDefinition]:
        """Return all registered task definitions."""
        return list(self._definitions.values())

    def contains(self, name: str) -> bool:
        """Check if a task name is registered."""
        return name in self._definitions

    # ── DB Sync ────────────────────────────────────────────────────────

    def sync_to_db(self, db: DBSession) -> None:
        """Sync all registered task definitions into the `tasks` table.

        Creates new rows for unregistered tasks; updates cron/timeout/retry
        config for existing ones but preserves `enabled` and `status`.
        """
        for definition in self._definitions.values():
            existing: TaskModel | None = (
                db.query(TaskModel)
                .filter(TaskModel.task_id == definition.name)
                .first()
            )
            if existing is None:
                task = TaskModel(
                    task_id=definition.name,
                    type=definition.type,
                    status="active",
                    trigger_type=definition.trigger_type,
                    cron_expr=definition.cron,
                    event_source=definition.event_source,
                    depends_on=json.dumps(definition.depends_on) if definition.depends_on else None,
                    retry_config=json.dumps({
                        "max_retries": definition.retry,
                        "backoff": definition.backoff,
                        "max_delay_seconds": definition.max_delay,
                    }),
                    timeout_seconds=definition.timeout,
                    mutex_enabled=definition.mutex,
                    enabled=True,
                    tags=json.dumps(definition.tags) if definition.tags else None,
                    description=definition.description,
                )
                db.add(task)
            else:
                # Update config fields (preserve enabled/status)
                existing.cron_expr = definition.cron
                existing.timeout_seconds = definition.timeout
                existing.retry_config = json.dumps({
                    "max_retries": definition.retry,
                    "backoff": definition.backoff,
                    "max_delay_seconds": definition.max_delay,
                })
                existing.depends_on = json.dumps(definition.depends_on) if definition.depends_on else None
                existing.mutex_enabled = definition.mutex
                existing.description = definition.description
        db.flush()

    # ── DB Query Helpers ───────────────────────────────────────────────

    def get_all_active_tasks(self, db: DBSession) -> list[TaskModel]:
        """Return all enabled tasks from the DB."""
        return (
            db.query(TaskModel)
            .filter(TaskModel.enabled == True)  # noqa: E712
            .all()
        )

    def get_task_model(self, db: DBSession, task_id: str) -> TaskModel | None:
        """Get a single TaskModel by ID."""
        return (
            db.query(TaskModel)
            .filter(TaskModel.task_id == task_id)
            .first()
        )

    @staticmethod
    def get_task_run(db: DBSession, run_id: int):
        """Get a single TaskRun by ID."""
        from app.models.task import TaskRun
        return db.query(TaskRun).filter(TaskRun.id == run_id).first()

    @staticmethod
    def get_last_run(db: DBSession, task_id: str):
        """Get the most recent TaskRun for a given task."""
        from app.models.task import TaskRun
        return (
            db.query(TaskRun)
            .filter(TaskRun.task_id == task_id)
            .order_by(TaskRun.created_at.desc())
            .first()
        )

    @staticmethod
    def parse_retry_config(retry_config_str: str | None) -> dict[str, Any]:
        """Safely parse retry_config JSON field."""
        if not retry_config_str:
            return {"max_retries": 0, "backoff": "none", "max_delay_seconds": 300}
        try:
            return json.loads(retry_config_str)
        except (json.JSONDecodeError, TypeError):
            return {"max_retries": 0, "backoff": "none", "max_delay_seconds": 300}


# ── Singleton ──────────────────────────────────────────────────────────

_registry = TaskRegistry()


def get_registry() -> TaskRegistry:
    """Get the global TaskRegistry singleton."""
    return _registry


# ── @task decorator ───────────────────────────────────────────────────

def task(
    name: str,
    type_: str = "job",
    trigger_type: str = "cron",
    cron: str | None = None,
    event_source: str | None = None,
    depends_on: list[str] | None = None,
    retry: int = 3,
    backoff: str = "exponential",
    max_delay: int = 300,
    timeout: int = 600,
    mutex: bool = True,
    tags: list[str] | None = None,
    description: str | None = None,
):
    """Decorator that registers a function as a Task.

    Usage:

        @task(name="daily_kline_sync", cron="0 18 * * 1-5", timeout=600)
        def my_task(ctx: TaskContext) -> dict:
            ...
    """
    def decorator(func: TaskFunc) -> TaskFunc:
        definition = TaskDefinition(
            name=name,
            func=func,
            type_=type_,
            trigger_type=trigger_type,
            cron=cron,
            event_source=event_source,
            depends_on=depends_on,
            retry=retry,
            backoff=backoff,
            max_delay=max_delay,
            timeout=timeout,
            mutex=mutex,
            tags=tags,
            description=description or func.__doc__,
        )
        _registry.register(definition)
        return func
    return decorator
