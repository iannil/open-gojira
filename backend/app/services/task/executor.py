"""TaskExecutor — dual-backend executor for sync and async tasks."""

import asyncio
import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from app.services.task.context import TaskContext

logger = logging.getLogger(__name__)


class TaskExecutor:
    """Executes task functions on either a ThreadPool (sync) or asyncio (async).

    Sync tasks:  dispatched to `ThreadPoolExecutor` (default 4 workers).
    Async tasks: dispatched to `asyncio.create_task()`.
    """

    def __init__(self, max_sync_workers: int = 4):
        self._sync_pool = ThreadPoolExecutor(
            max_workers=max_sync_workers,
            thread_name_prefix="task-worker",
        )
        self._run_map: dict[int, threading.Event | asyncio.Task] = {}
        self._lock = threading.Lock()

    # ── Public API ─────────────────────────────────────────────────────

    async def execute_sync(
        self,
        run_id: int,
        fn: Callable[[TaskContext], dict[str, Any]],
        ctx: TaskContext,
    ) -> dict[str, Any]:
        """Execute a synchronous function in the thread pool."""
        cancel_event = threading.Event()
        with self._lock:
            self._run_map[run_id] = cancel_event

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self._sync_pool,
                self._run_sync_safe,
                run_id, fn, ctx, cancel_event,
            )
            return result
        finally:
            with self._lock:
                self._run_map.pop(run_id, None)

    async def execute_async(
        self,
        run_id: int,
        fn: Callable[[TaskContext], dict[str, Any]],
        ctx: TaskContext,
    ) -> dict[str, Any]:
        """Execute an async function in the event loop."""
        async def wrapper():
            return await fn(ctx)

        task = asyncio.create_task(wrapper())
        with self._lock:
            self._run_map[run_id] = task

        try:
            return await task
        finally:
            with self._lock:
                self._run_map.pop(run_id, None)

    def cancel_run(self, run_id: int) -> bool:
        """Request cancellation of a running task by run_id.

        For sync tasks: sets a threading.Event flag.
        For async tasks: calls task.cancel().
        """
        with self._lock:
            entry = self._run_map.get(run_id)
            if entry is None:
                return False
            if isinstance(entry, threading.Event):
                entry.set()
                return True
            if isinstance(entry, asyncio.Task):
                entry.cancel()
                return True
            return False

    def shutdown(self, wait: bool = True, timeout: float | None = None) -> None:
        """Shutdown the thread pool."""
        self._sync_pool.shutdown(wait=wait)
        logger.info("TaskExecutor shutdown complete")

    @property
    def active_run_count(self) -> int:
        """Number of currently executing tasks."""
        with self._lock:
            return len(self._run_map)

    # ── Internal ───────────────────────────────────────────────────────

    @staticmethod
    def _run_sync_safe(
        run_id: int,
        fn: Callable[[TaskContext], dict[str, Any]],
        ctx: TaskContext,
        cancel_event: threading.Event,
    ) -> dict[str, Any]:
        """Wrap a sync function call with cancel-event monitoring.

        If the task has a custom `cancelled` check, we also propagate from our
        dedicated cancel_event (triggered by cancel_run).
        """
        original_cancel = ctx.cancel

        def enhanced_cancel():
            original_cancel()
            cancel_event.set()

        ctx.cancel = enhanced_cancel  # type: ignore[assignment]

        result = fn(ctx)
        return result
