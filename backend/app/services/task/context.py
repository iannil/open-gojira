"""TaskContext — runtime context passed to every task execution."""

import threading
import time
from collections.abc import Callable


class TaskContext:
    """Runtime context for a single Task execution.

    Provides progress reporting, cancellation signal, and shared state.
    Passed as the first argument to every @task-decorated function.
    """

    def __init__(
        self,
        task_id: str,
        run_id: int,
        trace_id: str | None = None,
        worker_id: str | None = None,
        triggered_by: str = "cron",
        on_progress: Callable[[float, str | None], None] | None = None,
    ):
        self.task_id = task_id
        self.run_id = run_id
        self.trace_id = trace_id
        self.worker_id = worker_id
        self.triggered_by = triggered_by
        self._on_progress = on_progress
        self._cancelled = threading.Event()
        self._started_at = time.monotonic()

    @property
    def cancelled(self) -> bool:
        """Check if this task has been requested to cancel."""
        return self._cancelled.is_set()

    def cancel(self) -> None:
        """Signal cancellation to the running task."""
        self._cancelled.set()

    def report_progress(self, progress: float, message: str | None = None) -> None:
        """Report execution progress (0.0 - 1.0)."""
        progress = max(0.0, min(1.0, progress))
        if self._on_progress:
            self._on_progress(progress, message)

    @property
    def elapsed_seconds(self) -> float:
        """Seconds since this task started executing."""
        return time.monotonic() - self._started_at
