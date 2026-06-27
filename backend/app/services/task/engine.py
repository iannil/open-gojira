"""TaskEngine — scheduling core for the unified task abstraction layer."""

import asyncio
import json
import logging
import threading
import time
import traceback
from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session as DBSession

from app.core.datetime_utils import now
from app.core.observability import _generate_id, get_logger
from app.db.session import SessionLocal
from app.models.task import Task as TaskModel, TaskRun
from app.services.scheduler_config_service import cron_to_trigger
from app.services.task.context import TaskContext
from app.services.task.dependency import DependencyChecker
from app.services.task.executor import TaskExecutor
from app.services.task.mutex import MutexLock
from app.services.task.registry import TaskDefinition, get_registry
from app.services.task.retry_manager import RetryManager
from app.services.task.timeout_watchdog import TimeoutWatchdog
from app.services.task.worker import WorkerManager

logger = logging.getLogger(__name__)


class TaskEngine:
    """Central scheduling engine for the unified Task abstraction.

    Responsibilities:
    - Cron trigger: ticks every second, checks for due cron tasks.
    - Dependency resolution: runs tasks only when upstream tasks are done.
    - Mutex: ensures one instance per task at a time.
    - Timeout watchdog: kills tasks exceeding their time limit.
    - Retry: automatic retry with exponential backoff.
    - Lifecycle: start/shutdown hooks for FastAPI lifespan.
    """

    def __init__(
        self,
        tick_interval: float = 1.0,
        cron_check_interval: int = 60,
        max_sync_workers: int = 4,
    ):
        self._tick_interval = tick_interval
        self._cron_check_interval = cron_check_interval
        self._last_cron_check: float = 0
        self._registry = get_registry()
        self._executor = TaskExecutor(max_sync_workers=max_sync_workers)
        self._worker_mgr = WorkerManager()
        self._watchdog = TimeoutWatchdog(
            check_interval=15.0,
            on_timeout=self._on_task_timeout,
        )
        self._dependency_checker = DependencyChecker()
        self._retry_manager = RetryManager()
        self._mutex = MutexLock()

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._running = False
        self._started_at: float | None = None

    # ── Properties ─────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def uptime_seconds(self) -> int | None:
        if self._started_at is None:
            return None
        return int(time.monotonic() - self._started_at)

    # ── Lifecycle ──────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the scheduling engine and watchdog thread."""
        if self._thread is not None:
            logger.warning("TaskEngine already running, ignoring start()")
            return

        # Sync registered tasks to DB
        try:
            with SessionLocal() as db:
                self._registry.sync_to_db(db)
                db.commit()
            logger.info("TaskRegistry synced to DB on startup")
        except Exception:
            logger.exception("Failed to sync TaskRegistry to DB on startup")

        self._started_at = time.monotonic()
        self._running = True
        self._stop_event.clear()
        self._watchdog.start()

        self._thread = threading.Thread(
            target=self._tick_loop,
            name="task-engine",
            daemon=True,
        )
        self._thread.start()

        # Recover: mark stale running tasks as failed
        try:
            with SessionLocal() as db:
                recovered = self._recover_stale_runs(db)
                db.commit()
                if recovered:
                    logger.info("Recovered %d stale task runs on startup", recovered)
        except Exception:
            logger.exception("Failed to recover stale task runs")

        logger.info("TaskEngine started (tick=%ss, workers=%d)", self._tick_interval, self._executor.active_run_count)

    def shutdown(self, wait: bool = True, timeout: float = 10.0) -> None:
        """Shutdown the engine, watchdog, and executor."""
        logger.info("TaskEngine shutting down...")
        self._running = False
        self._stop_event.set()
        self._watchdog.shutdown()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

        self._executor.shutdown(wait=wait, timeout=timeout)
        self._thread = None
        logger.info("TaskEngine shutdown complete")

    # ── Manual Task Control ────────────────────────────────────────────

    def trigger_task(
        self,
        task_id: str,
        db: DBSession,
        triggered_by: str = "api",
        input_data: dict[str, Any] | None = None,
    ) -> TaskRun:
        """Manually trigger a task, creating a queued TaskRun."""
        task_model = self._registry.get_task_model(db, task_id)
        if task_model is None:
            raise ValueError(f"Task '{task_id}' not found in database")

        if not task_model.enabled:
            raise ValueError(f"Task '{task_id}' is disabled")

        run = TaskRun(
            task_id=task_id,
            status="queued",
            triggered_by=triggered_by,
            trace_id=_generate_id(),
            input_data=json.dumps(input_data) if input_data else None,
        )
        db.add(run)
        # ── Sync Task business status ──
        task_model.status = "queued"
        db.flush()
        logger.info("Task %s manually triggered (run=%d, by=%s)", task_id, run.id, triggered_by)
        return run

    def cancel_task_run(self, run_id: int, db: DBSession) -> bool:
        """Cancel a queued or running task run."""
        run = self._registry.get_task_run(db, run_id)
        if run is None:
            return False

        if run.status == "queued":
            run.status = "cancelled"
            run.finished_at = now()
            # ── Sync Task business status ──
            task = self._registry.get_task_model(db, run.task_id)
            if task:
                task.status = "cancelled"
            db.flush()
            return True

        if run.status == "running":
            run.status = "cancelled"
            run.finished_at = now()
            # ── Sync Task business status ──
            task = self._registry.get_task_model(db, run.task_id)
            if task:
                task.status = "cancelled"
            db.flush()
            # Also tell the executor to cancel
            self._executor.cancel_run(run_id)
            self._watchdog.untrack(run_id)
            return True

        return False

    def pause_task(self, task_id: str, db: DBSession) -> bool:
        """Pause a cron-triggered task (prevent future runs)."""
        task_model = self._registry.get_task_model(db, task_id)
        if task_model is None:
            return False
        task_model.enabled = False
        db.flush()
        return True

    def resume_task(self, task_id: str, db: DBSession) -> bool:
        """Resume a paused task."""
        task_model = self._registry.get_task_model(db, task_id)
        if task_model is None:
            return False
        task_model.enabled = True
        task_model.status = "active"
        db.flush()
        return True

    # ── Health ─────────────────────────────────────────────────────────

    def get_health(self, db: DBSession) -> dict[str, Any]:
        """Get engine health status."""
        running_count = db.query(TaskRun).filter(TaskRun.status == "running").count()
        queued_count = db.query(TaskRun).filter(TaskRun.status == "queued").count()
        failed_24h = db.query(TaskRun).filter(
            TaskRun.status == "failed",
            TaskRun.created_at >= now(),
        ).count()

        return {
            "engine_running": self._running,
            "running_tasks": running_count,
            "queued_tasks": queued_count,
            "failed_tasks_24h": failed_24h,
            "workers_active": self._executor.active_run_count,
            "uptime_seconds": self.uptime_seconds,
        }

    # ── Query ──────────────────────────────────────────────────────────

    def enrich_task_response(
        self,
        task: TaskModel,
        db: DBSession,
    ) -> dict[str, Any]:
        """Build a dict from TaskModel + last run info for API responses."""
        last_run = self._registry.get_last_run(db, task.task_id)
        return {
            "task_id": task.task_id,
            "type": task.type,
            "status": task.status,
            "trigger_type": task.trigger_type,
            "cron_expr": task.cron_expr,
            "event_source": task.event_source,
            "depends_on": json.loads(task.depends_on) if task.depends_on else None,
            "retry_config": json.loads(task.retry_config) if task.retry_config else None,
            "timeout_seconds": task.timeout_seconds,
            "mutex_enabled": task.mutex_enabled,
            "enabled": task.enabled,
            "tags": json.loads(task.tags) if task.tags else None,
            "description": task.description,
            "next_run_time": task.cron_expr if task.enabled else None,
            "last_run_at": last_run.finished_at.isoformat() if last_run and last_run.finished_at else None,
            "last_run_status": last_run.status if last_run else None,
            "last_duration_ms": last_run.duration_ms if last_run else None,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        }

    def run_to_dict(self, run: TaskRun) -> dict[str, Any]:
        """Convert a TaskRun ORM object to a dict."""
        return {
            "id": run.id,
            "task_id": run.task_id,
            "status": run.status,
            "progress": run.progress,
            "progress_message": run.progress_message,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "duration_ms": run.duration_ms,
            "retry_count": run.retry_count,
            "max_retries": run.max_retries,
            "last_error": run.last_error,
            "result_summary": run.result_summary,
            "worker_id": run.worker_id,
            "triggered_by": run.triggered_by,
            "trace_id": run.trace_id,
            "created_at": run.created_at.isoformat() if run.created_at else None,
        }

    # ── Internal: Tick Loop ────────────────────────────────────────────

    def _tick_loop(self) -> None:
        """Main scheduling loop — runs in a background thread with a running event loop.

        Creates and runs an asyncio event loop so that _dispatch_run (which
        uses run_coroutine_threadsafe → _execute_and_finalize → execute_sync
        → loop.run_in_executor) actually executes instead of being queued on
        a dead loop. Without this, tasks stay "queued" forever.
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._async_tick())
        finally:
            loop.close()

    async def _async_tick(self) -> None:
        """Async tick loop — runs on a running event loop."""
        while not self._stop_event.is_set():
            try:
                # Check cron tasks periodically (not every tick)
                now_time = time.monotonic()
                if now_time - self._last_cron_check >= self._cron_check_interval:
                    self._check_cron_tasks()
                    self._last_cron_check = now_time

                self._process_pending_tasks()
            except Exception:
                logger.exception("TaskEngine tick error")
            await asyncio.sleep(self._tick_interval)

    def _process_pending_tasks(self) -> None:
        """Process one tick: pick up queued tasks and dispatch them."""
        with SessionLocal() as db:
            # Find all queued task runs
            queued_runs: list[TaskRun] = (
                db.query(TaskRun)
                .filter(TaskRun.status == "queued")
                .order_by(TaskRun.created_at.asc())
                .limit(10)
                .all()
            )

            for run in queued_runs:
                task_model = self._registry.get_task_model(db, run.task_id)
                if task_model is None:
                    # Task definition missing — mark run as failed
                    run.status = "failed"
                    run.last_error = f"[PERMANENT] Task definition '{run.task_id}' not found in registry"
                    run.finished_at = now()
                    # ── Sync Task business status ──
                    task = self._registry.get_task_model(db, run.task_id)
                    if task:
                        task.status = "failed"
                    continue

                if not task_model.enabled:
                    # Task is disabled — cancel the run
                    run.status = "cancelled"
                    run.finished_at = now()
                    # ── Sync Task business status ──
                    task_model.status = "cancelled"
                    continue

                # Check dependencies
                if task_model.depends_on:
                    satisfied, reason = self._dependency_checker.are_dependencies_satisfied(db, task_model)
                    if not satisfied:
                        # Leave it queued; check again next tick
                        continue

                # Check mutex
                if task_model.mutex_enabled:
                    if not self._mutex.try_acquire(db, run.task_id, run.id):
                        # Another instance is running; leave queued
                        continue

                # Get task definition from registry
                definition = self._registry.get(run.task_id)
                if definition is None and task_model.type == "job":
                    # Registered via DB but not via @task decorator yet (compat mode)
                    # This happens in Phase 1 for tasks not yet wrapped
                    logger.debug("Skipping task %s (no @task decorator registered yet)", run.task_id)
                    continue

                if definition is None:
                    continue

                # Dispatch the run
                self._dispatch_run(db, run, task_model, definition)

            db.commit()

    def _check_cron_tasks(self) -> None:
        """Check all enabled cron tasks and create TaskRun entries for due tasks.

        Uses APScheduler CronTrigger to evaluate whether a cron expression
        fires in the current time window (since the last check).
        """
        from datetime import datetime as dt, timedelta

        try:
            with SessionLocal() as db:
                cron_tasks = (
                    db.query(TaskModel)
                    .filter(
                        TaskModel.enabled == True,  # noqa: E712
                        TaskModel.trigger_type == "cron",
                        TaskModel.cron_expr.isnot(None),
                    )
                    .all()
                )

                now_dt = now()
                check_window = max(self._cron_check_interval, 30)
                window_start = now_dt - timedelta(seconds=check_window)

                for task in cron_tasks:
                    try:
                        trigger = cron_to_trigger(task.cron_expr)
                    except Exception:
                        logger.warning(
                            "Invalid cron expression for task %s: %s",
                            task.task_id, task.cron_expr,
                        )
                        continue

                    # Check if the cron fires in our time window
                    next_fire = trigger.get_next_fire_time(None, window_start)
                    if next_fire and next_fire <= now_dt:
                        # Check if there's already a queued or running run
                        existing = (
                            db.query(TaskRun)
                            .filter(
                                TaskRun.task_id == task.task_id,
                                TaskRun.status.in_(["queued", "running"]),
                            )
                            .first()
                        )
                        if existing is None:
                            run = TaskRun(
                                task_id=task.task_id,
                                status="queued",
                                triggered_by="cron",
                                max_retries=(
                                    json.loads(task.retry_config).get("max_retries", 3)
                                    if task.retry_config else 3
                                ),
                                trace_id=_generate_id(),
                            )
                            db.add(run)
                            # ── Sync Task business status ──
                            task.status = "queued"
                            logger.info(
                                "Cron task %s triggered at %s",
                                task.task_id, now_dt.isoformat(),
                            )

                db.commit()
        except Exception:
            logger.exception("Error checking cron tasks")

    def _dispatch_run(
        self,
        db: DBSession,
        run: TaskRun,
        task_model: TaskModel,
        definition: TaskDefinition,
    ) -> None:
        """Dispatch a single TaskRun to the executor."""
        # Mark as running
        run.status = "running"
        task_model.status = "running"  # ── Sync business status ──
        run.started_at = now()
        run.worker_id = self._worker_mgr.worker_id

        # Create TaskContext
        _run_id = run.id
        ctx = TaskContext(
            task_id=run.task_id,
            run_id=_run_id,
            trace_id=run.trace_id,
            worker_id=run.worker_id,
            triggered_by=run.triggered_by,
            on_progress=lambda p, msg, rid=_run_id: self._update_progress(
                rid, p, msg,
            ),
        )

        # Track timeout
        timeout = task_model.timeout_seconds or definition.timeout
        self._watchdog.track(run.id, time.monotonic(), timeout)
        self._worker_mgr.start_run(run.id, run.task_id)
        db.flush()

        # Execute async in the event loop
        loop = self._get_event_loop()
        future = asyncio.run_coroutine_threadsafe(
            self._execute_and_finalize(run.id, definition.func, ctx, timeout),
            loop,
        )

    def _get_event_loop(self):
        """Get or create an asyncio event loop for the engine thread."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop

    async def _execute_and_finalize(
        self,
        run_id: int,
        fn: Callable[[TaskContext], dict[str, Any]],
        ctx: TaskContext,
        timeout: int,
    ) -> None:
        """Execute the task function and finalize the run in DB."""
        try:
            result = await asyncio.wait_for(
                self._executor.execute_sync(run_id, fn, ctx),
                timeout=timeout,
            )
            self._finalize_run(run_id, success=True, result=result)
        except asyncio.TimeoutError:
            self._finalize_run(
                run_id,
                success=False,
                error=f"[TRANSIENT] Task timed out after {timeout}s",
            )
        except asyncio.CancelledError:
            self._finalize_run(
                run_id,
                success=False,
                error="[TRANSIENT] Task cancelled",
            )
        except Exception as exc:
            self._finalize_run(
                run_id,
                success=False,
                error=f"{type(exc).__name__}: {exc}",
            )

    def _finalize_run(
        self,
        run_id: int,
        success: bool,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        """Update the TaskRun status in the database after execution."""
        self._watchdog.untrack(run_id)
        self._worker_mgr.end_run(run_id)
        finished_at = now()

        try:
            with SessionLocal() as db:
                run = db.query(TaskRun).filter(TaskRun.id == run_id).first()
                if run is None:
                    return

                run.finished_at = finished_at
                run.duration_ms = int(
                    (finished_at - run.started_at).total_seconds() * 1000
                ) if run.started_at else None

                if success:
                    run.status = "success"
                    if result:
                        run.result_summary = json.dumps(result, default=str)[:2000]
                else:
                    run.status = "failed"
                    run.last_error = (error or "Unknown error")[:2000]

                    # Check retry
                    task_model = self._registry.get_task_model(db, run.task_id)
                    if task_model and task_model.retry_config:
                        config = RetryManager.parse_config(task_model.retry_config)
                        retry_run = RetryManager.schedule_retry(db, run, config)
                        if retry_run:
                            run.last_error = (run.last_error or "") + " [retry scheduled]"

                # ── Sync Task business status to match this run ──
                task = self._registry.get_task_model(db, run.task_id)
                if task:
                    task.status = "active" if success else "failed"

                db.commit()
        except Exception:
            logger.exception("Failed to finalize task run=%d", run_id)

    def _update_progress(self, run_id: int, progress: float, message: str | None) -> None:
        """Update the progress of a running task run."""
        try:
            with SessionLocal() as db:
                run = db.query(TaskRun).filter(TaskRun.id == run_id).first()
                if run and run.status == "running":
                    run.progress = progress
                    if message:
                        run.progress_message = message[:500]
                    db.commit()
        except Exception:
            pass  # Best-effort progress update

    def _on_task_timeout(self, run_id: int) -> None:
        """Callback invoked by TimeoutWatchdog when a task times out."""
        try:
            with SessionLocal() as db:
                run = db.query(TaskRun).filter(TaskRun.id == run_id).first()
                if run and run.status == "running":
                    run.status = "failed"
                    run.last_error = f"[TRANSIENT] Task timed out after {run.duration_ms}ms"
                    run.finished_at = now()
                    # Cancel the executor thread
                    self._executor.cancel_run(run_id)
                    self._worker_mgr.end_run(run_id)
                    # ── Sync Task business status ──
                    task = self._registry.get_task_model(db, run.task_id)
                    if task:
                        task.status = "failed"
                    db.commit()
                    logger.warning("Task run=%d marked as failed due to timeout", run_id)
        except Exception:
            logger.exception("Timeout handler error for run=%d", run_id)

    def _recover_stale_runs(self, db: DBSession) -> int:
        """Mark any 'running' or 'queued' task runs as failed on startup.

        Catches runs left behind by a process crash or kill -9.
        """
        stale = (
            db.query(TaskRun)
            .filter(TaskRun.status.in_(["running", "queued"]))
            .all()
        )
        now_ts = now()
        count = 0
        for run in stale:
            run.status = "failed"
            run.last_error = "[RECOVERED] Process restarted while task was in progress"
            run.finished_at = now_ts
            # ── Sync Task business status ──
            task = self._registry.get_task_model(db, run.task_id)
            if task:
                task.status = "failed"
            count += 1

        # ── Recover business entities stuck in transient states ──
        self._recover_stuck_theme_scan_reports(db)

        return count

    def _recover_stuck_theme_scan_reports(self, db: DBSession) -> None:
        """Recover ThemeScanReport placeholders left in 'running' status by a crash."""
        try:
            from app.models.theme_scan_report import STATUS_FAILED, ThemeScanReport
            stuck = (
                db.query(ThemeScanReport)
                .filter(ThemeScanReport.status == "running")
                .all()
            )
            for r in stuck:
                r.status = STATUS_FAILED
            if stuck:
                logger.info("Recovered %d stuck ThemeScanReport(s) on startup", len(stuck))
        except Exception:
            logger.exception("Failed to recover stuck ThemeScanReports")
