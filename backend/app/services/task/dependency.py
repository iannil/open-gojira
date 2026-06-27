"""Dependency checker — verifies upstream tasks before execution."""

import json
import logging

from sqlalchemy.orm import Session as DBSession

from app.models.task import Task as TaskModel, TaskRun

logger = logging.getLogger(__name__)


class DependencyChecker:
    """Checks whether a task's dependencies are satisfied before execution."""

    @staticmethod
    def get_depends_on(task: TaskModel) -> list[str]:
        """Parse the depends_on JSON field."""
        if not task.depends_on:
            return []
        try:
            return json.loads(task.depends_on)
        except (json.JSONDecodeError, TypeError):
            return []

    @staticmethod
    def are_dependencies_satisfied(db: DBSession, task: TaskModel) -> tuple[bool, str | None]:
        """Check if all upstream tasks have completed successfully.

        Returns (True, None) if all satisfied, or (False, reason) if blocked.
        """
        deps = DependencyChecker.get_depends_on(task)
        if not deps:
            return True, None

        unsatisfied: list[str] = []
        for dep_id in deps:
            last_run: TaskRun | None = (
                db.query(TaskRun)
                .filter(TaskRun.task_id == dep_id)
                .order_by(TaskRun.created_at.desc())
                .first()
            )
            if last_run is None:
                unsatisfied.append(f"'{dep_id}' has never run")
            elif last_run.status not in ("success",):
                unsatisfied.append(
                    f"'{dep_id}' last run status={last_run.status}, not 'success'"
                )

        if unsatisfied:
            return False, "; ".join(unsatisfied)
        return True, None

    @staticmethod
    def get_blocked_downstream_tasks(db: DBSession, task_id: str) -> list[TaskModel]:
        """Find all tasks that depend on the given task_id and are blocked."""
        all_tasks = db.query(TaskModel).filter(TaskModel.enabled == True).all()  # noqa: E712
        blocked: list[TaskModel] = []
        for t in all_tasks:
            deps = DependencyChecker.get_depends_on(t)
            if task_id in deps:
                blocked.append(t)
        return blocked
