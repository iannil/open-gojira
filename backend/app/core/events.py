"""Process-internal synchronous event bus.

Zero external dependencies. Handlers run synchronously during emit().
A handler exception is caught and logged — it does NOT block subsequent handlers.
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from pydantic import BaseModel, Field

from app.core.datetime_utils import utcnow

try:
    from app.core.observability import _generate_id
except ImportError:
    import uuid
    def _generate_id() -> str:
        return uuid.uuid4().hex[:16]

logger = logging.getLogger(__name__)

# ── Thread pool executor for async dispatch ────────────────────────────────

_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()


def _get_executor() -> ThreadPoolExecutor:
    """Get or create the shared thread pool executor."""
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="eventbus")
    return _executor


def shutdown_executor(wait: bool = True, timeout: float = 10.0) -> None:
    """Shutdown the event dispatch executor. Call on app shutdown."""
    global _executor
    with _executor_lock:
        if _executor is not None:
            _executor.shutdown(wait=wait, cancel_futures=False)
            _executor = None


# ── Event base ──────────────────────────────────────────────────────────────


class BaseEvent(BaseModel):
    """Base class for all events."""
    event_id: str = Field(default_factory=_generate_id)
    trace_id: str = Field(default_factory=_generate_id)
    timestamp: object = Field(default_factory=utcnow)


# ── Domain events ───────────────────────────────────────────────────────────


class DataSyncCompleted(BaseEvent):
    pipeline_type: str
    stock_codes: list[str]
    run_id: str
    status: str
    completed_items: int = 0
    failed_items: int = 0


class PlanEvaluationCompleted(BaseEvent):
    plan_id: int
    plan_name: str
    scanned: int = 0
    passed: int = 0
    drafts_emitted: int = 0
    errors: int = 0


class DraftCreated(BaseEvent):
    draft_id: int
    stock_code: str
    direction: str
    plan_id: int | None = None
    add_pct: float | None = None
    reduce_pct_of_position: float | None = None


class AlertTriggered(BaseEvent):
    alert_event_id: int
    rule_id: int
    stock_code: str | None = None
    title: str
    severity: str = "info"


# ── Serenity research events (Q10/Q17) ─────────────────────────────────────


class ResearchRunCompleted(BaseEvent):
    run_id: int
    research_theme_id: int
    research_theme_name: str
    company_count: int = 0
    evidence_count: int = 0
    ranking_count: int = 0
    token_input: int = 0
    token_output: int = 0
    elapsed_sec: float = 0.0


class ResearchRunFailed(BaseEvent):
    run_id: int
    research_theme_id: int
    research_theme_name: str
    error: str
    attempt_count: int = 1


class MonthlyBudgetExceeded(BaseEvent):
    month: str  # YYYY-MM
    spend_cny: float
    budget_cny: float
    triggered_by_run_id: int | None = None


# ── Thesis monitor events (Phase 2 #9 阶段 B v2, 2026-06-16) ────────────────


class ClaimVariablesProposed(BaseEvent):
    """Emitted after propose_for_run completes (success or partial).

    UI Cockpit badge picks this up via polling GET /api/cockpit/claim-variables-pending.
    """
    run_id: int
    proposed_count: int
    skipped_count: int = 0
    failed_count: int = 0  # claims that errored during parse/persist


class ThesisAlertTriggered(BaseEvent):
    """Emitted when check_claim_variables detects a breach.

    Handler routes to notification_service.send() via NotificationChannel.
    Dedup is enforced upstream via last_alerted_at (7-day window).
    """
    claim_var_id: int
    code: str
    stock_name: str
    variable_name: str
    current_value: float | None
    threshold_value: float
    breach_when: str  # "lt" | "gt"
    window_periods: int | None
    message: str


# ── EventBus ────────────────────────────────────────────────────────────────

Handler = Callable[[BaseEvent], None]


class EventBus:
    """Synchronous in-process event bus."""

    def __init__(self) -> None:
        self._handlers: dict[type[BaseEvent], list[Handler]] = {}
        self._lock = threading.Lock()

    def subscribe(self, event_type: type[BaseEvent], handler: Handler) -> None:
        with self._lock:
            self._handlers.setdefault(event_type, []).append(handler)

    def emit(self, event: BaseEvent) -> None:
        handlers = self._handlers.get(type(event), [])
        if not handlers:
            return
        start = time.monotonic()
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                logger.exception(
                    "EventBus_Handler_Error event_type=%s handler=%s",
                    type(event).__name__,
                    handler.__qualname__,
                )
        elapsed_ms = (time.monotonic() - start) * 1000
        logger.info(
            "EventBus_Emit event_type=%s handlers=%d elapsed_ms=%.1f",
            type(event).__name__,
            len(handlers),
            elapsed_ms,
        )

    def emit_async(self, event: BaseEvent) -> None:
        """Dispatch event to handlers in background threads.

        Returns immediately without waiting for handlers. Use for
        request-path events that shouldn't block the response.
        """
        handlers = self._handlers.get(type(event), [])
        if not handlers:
            return
        executor = _get_executor()
        for handler in handlers:
            executor.submit(self._safe_call, handler, event)

    def _safe_call(self, handler: Handler, event: BaseEvent) -> None:
        """Call a handler, logging exceptions instead of propagating."""
        try:
            handler(event)
        except Exception:
            logger.exception(
                "EventBus_AsyncHandler_Error event_type=%s handler=%s",
                type(event).__name__,
                handler.__qualname__,
            )

    def get_registry(self) -> dict[type[BaseEvent], list[str]]:
        with self._lock:
            return {
                et: [h.__qualname__ for h in hs]
                for et, hs in self._handlers.items()
            }


bus = EventBus()
