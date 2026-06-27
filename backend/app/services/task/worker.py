"""Worker manager — tracks worker identity and heartbeats."""

import logging
import threading
import uuid

logger = logging.getLogger(__name__)


class WorkerManager:
    """Manages worker identity and heartbeats for the task execution pool.

    Each TaskEngine instance gets a unique worker_id that survives for
    the lifetime of the process. Used for tracking which process executed
    which task run.
    """

    def __init__(self):
        self._worker_id = f"worker-{uuid.uuid4().hex[:12]}"
        self._active_runs: dict[int, str] = {}  # run_id -> task_id
        self._lock = threading.Lock()

    @property
    def worker_id(self) -> str:
        return self._worker_id

    def start_run(self, run_id: int, task_id: str) -> None:
        """Register a run as being executed by this worker."""
        with self._lock:
            self._active_runs[run_id] = task_id

    def end_run(self, run_id: int) -> None:
        """Unregister a completed/failed run."""
        with self._lock:
            self._active_runs.pop(run_id, None)

    def get_active_runs(self) -> dict[int, str]:
        """Get all currently active runs for this worker."""
        with self._lock:
            return dict(self._active_runs)

    @property
    def active_count(self) -> int:
        """Number of currently active runs on this worker."""
        with self._lock:
            return len(self._active_runs)
