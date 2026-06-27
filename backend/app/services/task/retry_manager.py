"""Retry manager — handles exponential backoff retry scheduling."""

import json
import logging
import time
from typing import Any

from sqlalchemy.orm import Session as DBSession

from app.models.task import TaskRun

logger = logging.getLogger(__name__)


class RetryManager:
    """Manages task retry logic with configurable backoff strategies."""

    BACKOFF_STRATEGIES = ("exponential", "linear", "fixed", "none")

    @staticmethod
    def parse_config(retry_config_str: str | None) -> dict[str, Any]:
        """Parse retry_config JSON from the Task model."""
        if not retry_config_str:
            return {"max_retries": 3, "backoff": "exponential", "max_delay_seconds": 300}
        try:
            cfg = json.loads(retry_config_str)
            if not isinstance(cfg, dict):
                return {"max_retries": 3, "backoff": "exponential", "max_delay_seconds": 300}
            return cfg
        except (json.JSONDecodeError, TypeError):
            return {"max_retries": 3, "backoff": "exponential", "max_delay_seconds": 300}

    @staticmethod
    def get_wait_seconds(retry_count: int, config: dict[str, Any]) -> int:
        """Calculate wait time before the next retry attempt."""
        backoff = config.get("backoff", "exponential")
        max_delay = config.get("max_delay_seconds", 300)

        if backoff == "none":
            return 0
        if backoff == "fixed":
            return min(60, max_delay)
        if backoff == "linear":
            return min(retry_count * 30, max_delay)
        # exponential: 2^retry * 10, capped at max_delay
        wait = (2 ** retry_count) * 10
        return min(wait, max_delay)

    @staticmethod
    def should_retry(
        db: DBSession,
        run: TaskRun,
    ) -> bool:
        """Determine if a failed run should be retried.

        Returns True if retry_count < max_retries AND error is transient.
        """
        if run.retry_count >= run.max_retries:
            return False

        # Permanent errors are not retried (indicated by specific error prefix)
        if run.last_error and run.last_error.startswith("[PERMANENT]"):
            return False

        return True

    @staticmethod
    def should_retry_from_config(
        db: DBSession,
        run: TaskRun,
        config: dict[str, Any],
    ) -> bool:
        """Determine if a failed run should be retried, using parsed config."""
        max_retries = config.get("max_retries", 3)
        if run.retry_count >= max_retries:
            return False
        if run.last_error and run.last_error.startswith("[PERMANENT]"):
            return False
        return True

    @staticmethod
    def schedule_retry(
        db: DBSession,
        run: TaskRun,
        config: dict[str, Any],
    ) -> TaskRun | None:
        """Schedule a retry by creating a new queued TaskRun.

        Returns the new TaskRun if a retry was scheduled, None otherwise.
        """
        from app.models.task import TaskRun as NewTaskRun

        if not RetryManager.should_retry_from_config(db, run, config):
            return None

        wait_seconds = RetryManager.get_wait_seconds(run.retry_count, config)
        # For simplicity, we create a new run immediately; the engine
        # respects retry_count for ordering. The wait is managed by
        # the engine's retry scheduling loop.
        new_run = NewTaskRun(
            task_id=run.task_id,
            status="queued",
            retry_count=run.retry_count + 1,
            max_retries=run.max_retries,
            triggered_by="retry",
            trace_id=run.trace_id,
        )
        db.add(new_run)
        db.flush()
        logger.info(
            "Scheduled retry %d/%d for task=%s (wait=%ds)",
            new_run.retry_count,
            new_run.max_retries,
            run.task_id,
            wait_seconds,
        )
        return new_run
