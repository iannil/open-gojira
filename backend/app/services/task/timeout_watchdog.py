"""Timeout watchdog — monitors running tasks for timeout violations."""

import logging
import threading
import time

logger = logging.getLogger(__name__)


class TimeoutWatchdog:
    """Background thread that periodically checks for timed-out task runs.

    Runs every `check_interval` seconds. When a task exceeds its
    `timeout_seconds`, the watchdog calls the provided `on_timeout` callback.
    """

    def __init__(
        self,
        check_interval: float = 15.0,
        on_timeout=None,
    ):
        self._check_interval = check_interval
        self._on_timeout = on_timeout
        self._running_tasks: dict[int, _TrackedRun] = {}
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        """Start the watchdog background thread."""
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="timeout-watchdog",
            daemon=True,
        )
        self._thread.start()
        logger.info("TimeoutWatchdog started (interval=%ss)", self._check_interval)

    def shutdown(self) -> None:
        """Stop the watchdog thread."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None
        logger.info("TimeoutWatchdog stopped")

    def track(self, run_id: int, started_at: float, timeout_seconds: int) -> None:
        """Start tracking a task run for timeout."""
        with self._lock:
            self._running_tasks[run_id] = _TrackedRun(
                run_id=run_id,
                started_at=started_at,
                timeout_seconds=timeout_seconds,
            )

    def untrack(self, run_id: int) -> None:
        """Stop tracking a task run (called when it finishes)."""
        with self._lock:
            self._running_tasks.pop(run_id, None)

    @property
    def active_count(self) -> int:
        """Number of currently tracked tasks."""
        with self._lock:
            return len(self._running_tasks)

    # ── Internal ───────────────────────────────────────────────────────

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            self._check_timeouts()
            self._stop_event.wait(self._check_interval)

    def _check_timeouts(self) -> None:
        now = time.monotonic()
        timed_out: list[_TrackedRun] = []
        with self._lock:
            for run_id, tracked in list(self._running_tasks.items()):
                elapsed = now - tracked.started_at
                if elapsed > tracked.timeout_seconds:
                    timed_out.append(tracked)
                    del self._running_tasks[run_id]

        for tracked in timed_out:
            logger.warning(
                "Task run=%d timed out after %ds (limit=%ds)",
                tracked.run_id,
                round(time.monotonic() - tracked.started_at),
                tracked.timeout_seconds,
            )
            if self._on_timeout:
                try:
                    self._on_timeout(tracked.run_id)
                except Exception:
                    logger.exception(
                        "TimeoutWatchdog on_timeout callback failed for run=%d",
                        tracked.run_id,
                    )


class _TrackedRun:
    """Internal struct for a tracked task run."""
    __slots__ = ("run_id", "started_at", "timeout_seconds")

    def __init__(self, run_id: int, started_at: float, timeout_seconds: int):
        self.run_id = run_id
        self.started_at = started_at
        self.timeout_seconds = timeout_seconds
