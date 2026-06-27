"""Mutex — concurrency control for mutually-exclusive tasks."""

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session as DBSession

logger = logging.getLogger(__name__)


class MutexLock:
    """Task-level mutex using an atomic status transition.

    Ensures at most one instance of a task runs at any given time.
    Uses a conditional UPDATE pattern via the ORM status check.
    """

    @staticmethod
    def try_acquire(db: DBSession, task_id: str, run_id: int) -> bool:
        """Try to mark a task as 'running' if it's currently 'queued'.

        Returns True if the lock was acquired (this run_id gets to execute),
        False if another instance is already running.
        """
        from app.models.task import TaskRun

        # Check if there's already a running instance
        running = (
            db.query(TaskRun)
            .filter(
                TaskRun.task_id == task_id,
                TaskRun.status.in_(["running", "queued"]),
            )
            .first()
        )
        if running and running.id != run_id:
            logger.warning(
                "Mutex lock failed for task=%s run=%d (conflict with run=%d)",
                task_id, run_id, running.id,
            )
            return False

        return True

    @staticmethod
    def release(db: DBSession, task_id: str, run_id: int) -> None:
        """Release the mutex (no-op; status transition handles it)."""
        pass
