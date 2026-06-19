"""Scheduler alerting + Pipeline freshness tracking.

S3.5 integrates S3.1-S3.4 infrastructure into the runtime:

1. ``with_alerting(job_id)`` — decorator that wraps a scheduler job with
   try/except → emits a ``critical`` system_alert on failure. Deduplicates
   within a 10-minute window to avoid alert spam during recurring failures.

2. ``record_pipeline_completion(db, category, success, count, error)`` —
   helper that updates the ``data_freshness`` table after each Pipeline
   run. Called from Pipeline completion hooks (manager.py / scheduler.py).

The decorator opens its own short-lived DB session (it must not assume the
caller has one — scheduler jobs run in their own thread). For tests that
need to assert on the alert, ``app.services.scheduler_alerting.SessionLocal``
can be monkey-patched to point at the test's in-memory engine.
"""
from __future__ import annotations
from app.core.datetime_utils import now

import functools
import logging
import traceback
from datetime import datetime, timezone
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.services.data_freshness_service import (
    record_sync_failure,
    record_sync_success,
)
from app.services.system_alert_service import create_alert


logger = logging.getLogger(__name__)


# Dedup window — repeated failures within this many seconds of the last emit
# are suppressed (1 alert per window per job_id).
DEDUP_WINDOW_SECONDS = 600  # 10 min

# Module-level state for the dedup mechanism. Process-local — fine for a
# single-process scheduler. If the scheduler ever fans out to multiple
# processes, replace with a shared store (Redis SETEX, etc.).
_last_emit_at: dict[str, datetime] = {}


def _utcnow_naive() -> datetime:
    return now()


def _should_emit(job_id: str, now: datetime) -> bool:
    """Return True if enough time has elapsed since the last emit."""
    last = _last_emit_at.get(job_id)
    if last is None:
        return True
    return (now - last).total_seconds() > DEDUP_WINDOW_SECONDS


def _mark_emitted(job_id: str, now: datetime) -> None:
    _last_emit_at[job_id] = now


def reset_dedup_state() -> None:
    """Clear dedup bookkeeping. Used by tests to keep runs isolated."""
    _last_emit_at.clear()


def emit_job_failure_alert(
    db: Session,
    *,
    job_id: str,
    error: BaseException,
) -> None:
    """Create a system_alert for a failed scheduler job.

    Deduplicated within ``DEDUP_WINDOW_SECONDS`` — repeated failures of the
    same ``job_id`` only emit one alert per window. Caller is responsible
    for committing the session.
    """
    now = _utcnow_naive()
    if not _should_emit(job_id, now):
        return
    try:
        create_alert(
            db,
            severity="critical",
            category="scheduler",
            message=(
                f"Scheduled job '{job_id}' failed: "
                f"{type(error).__name__}: {str(error)[:200]}"
            ),
            detail={
                "job_id": job_id,
                "error_type": type(error).__name__,
                "error_message": str(error)[:500],
                "traceback": traceback.format_exc()[:2000],
            },
        )
        _mark_emitted(job_id, now)
    except Exception as emit_err:
        logger.error(
            "Failed to emit scheduler alert for %s: %s", job_id, emit_err,
        )


def with_alerting(job_id: str) -> Callable:
    """Decorator: wrap a scheduler job with system_alert emission.

    The wrapped function re-raises the original exception after attempting
    to emit the alert, so callers (e.g. APScheduler / ``_with_tracking``)
    still observe the failure.
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                db = SessionLocal()
                try:
                    emit_job_failure_alert(db, job_id=job_id, error=e)
                    db.commit()
                except Exception:
                    logger.exception(
                        "with_alerting: DB failure while emitting alert for %s",
                        job_id,
                    )
                finally:
                    db.close()
                raise

        return wrapper

    return decorator


def record_pipeline_completion(
    db: Session,
    category: str,
    *,
    success: bool,
    record_count: Optional[int] = None,
    error: Optional[str] = None,
) -> None:
    """Update ``data_freshness`` after a Pipeline run.

    Call from Pipeline completion hooks (manager.py / scheduler jobs that
    drive syncs). The caller owns the transaction; this function only
    ``flush()``es pending changes.
    """
    if success:
        record_sync_success(db, category, record_count=record_count or 0)
    else:
        record_sync_failure(db, category, error=error or "unknown error")
    db.flush()
