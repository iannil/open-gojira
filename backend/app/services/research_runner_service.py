"""Serenity research runner — orchestrates LLM call + persist + events.

Implements:
- Q10 async execution via dedicated ThreadPoolExecutor (separate from EventBus
  pool so 5-minute runs don't block alert handlers)
- Q13 triple hard constraint (max_tokens / max_searches / timeout)
- Q8 retry on failure
- Q17 EventBus emit (ResearchRunCompleted / ResearchRunFailed / MonthlyBudgetExceeded)
- Q6 rate limit per theme (default 5 minutes)
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.events import (
    MonthlyBudgetExceeded,
    ResearchRunCompleted,
    ResearchRunFailed,
    bus,
)
from app.core.research_config import SERENITY_RUN_CONFIG
from app.db.session import SessionLocal
from app.models.research_run import ResearchRun
from app.models.research_theme import ResearchTheme
from app.services.llm.zhipu_client import ZhipuClient, ZhipuClientError
from app.services.research_context_builder import build_user_context
from app.services.research_persistence_service import (
    ResearchPersistenceError,
    persist_research_result,
)

logger = logging.getLogger(__name__)


# ── Dedicated executor (not shared with EventBus) ───────────────────────
_runner_executor: ThreadPoolExecutor | None = None
_runner_executor_lock = threading.Lock()


def _get_runner_executor() -> ThreadPoolExecutor:
    global _runner_executor
    with _runner_executor_lock:
        if _runner_executor is None:
            _runner_executor = ThreadPoolExecutor(
                max_workers=2,  # concurrent serenity runs (token cost concern)
                thread_name_prefix="serenity-runner",
            )
    return _runner_executor


def shutdown_runner_executor(wait: bool = True, timeout: float = 30.0) -> None:
    """Test/app-shutdown hook."""
    global _runner_executor
    with _runner_executor_lock:
        if _runner_executor is not None:
            _runner_executor.shutdown(wait=wait, cancel_futures=False)
            _runner_executor = None


# ── Errors ──────────────────────────────────────────────────────────────
class ResearchRunnerError(Exception):
    """Raised on trigger-time validation (before submission to executor)."""


# ── Public API ──────────────────────────────────────────────────────────
def trigger_run(
    db: Session,
    theme_id: int,
    triggered_by: str = "manual",
    market: str | None = None,
    time_window: str | None = None,
) -> ResearchRun:
    """Create a ResearchRun(status='running') and submit to background executor.

    Returns immediately with the run row. Caller polls status via run_id.
    Raises ResearchRunnerError on validation failure.
    """
    theme = db.query(ResearchTheme).filter(ResearchTheme.id == theme_id).first()
    if not theme:
        raise ResearchRunnerError(f"ResearchTheme id={theme_id} not found")
    if theme.status != "active":
        raise ResearchRunnerError(
            f"ResearchTheme id={theme_id} status={theme.status}, must be 'active'"
        )

    # Q6 rate limit
    if theme.last_run_at:
        elapsed_min = (datetime.utcnow() - theme.last_run_at).total_seconds() / 60
        min_gap = SERENITY_RUN_CONFIG["rate_limit_per_theme_minutes"]
        if elapsed_min < min_gap:
            raise ResearchRunnerError(
                f"Theme '{theme.name}' was run {elapsed_min:.1f} minutes ago; "
                f"wait {min_gap - elapsed_min:.1f} more minutes"
            )

    scope_market = market or theme.market
    scope_tw = time_window or "3-12M"

    run = ResearchRun(
        research_theme_id=theme.id,
        status="running",
        scope_market=scope_market,
        scope_time_window=scope_tw,
        triggered_by=triggered_by,
        llm_provider=SERENITY_RUN_CONFIG["default_model"],
        attempt_count=1,
    )
    db.add(run)
    db.flush()

    # Detach IDs for worker (don't pass ORM objects across threads)
    run_id = run.id
    theme_id_for_worker = theme.id
    theme_name_for_worker = theme.name
    scope_market_for_worker = scope_market
    scope_tw_for_worker = scope_tw

    # Submit to background — uses its own DB session
    _get_runner_executor().submit(
        _execute_run_in_worker,
        run_id=run_id,
        theme_id=theme_id_for_worker,
        theme_name=theme_name_for_worker,
        scope_market=scope_market_for_worker,
        scope_time_window=scope_tw_for_worker,
    )

    return run


def _execute_run_in_worker(
    run_id: int,
    theme_id: int,
    theme_name: str,
    scope_market: str,
    scope_time_window: str,
) -> None:
    """Worker-thread entry point. Owns its own DB session."""
    db = SessionLocal()
    started = time.monotonic()
    try:
        _execute_run_with_retry(
            db=db,
            run_id=run_id,
            theme_id=theme_id,
            theme_name=theme_name,
            scope_market=scope_market,
            scope_time_window=scope_time_window,
            started=started,
        )
    except Exception:
        logger.exception("Serenity worker crashed for run_id=%s", run_id)
    finally:
        db.close()


def _execute_run_with_retry(
    db: Session,
    run_id: int,
    theme_id: int,
    theme_name: str,
    scope_market: str,
    scope_time_window: str,
    started: float,
) -> None:
    """Single attempt with up to retry_on_failure retries."""
    max_attempts = 1 + SERENITY_RUN_CONFIG["retry_on_failure"]
    last_error: str = ""

    for attempt in range(1, max_attempts + 1):
        run = db.query(ResearchRun).filter(ResearchRun.id == run_id).first()
        if not run:
            logger.error("ResearchRun id=%s disappeared mid-flight", run_id)
            return
        run.attempt_count = attempt
        db.flush()

        try:
            _execute_single_attempt(
                db=db,
                run=run,
                theme_id=theme_id,
                theme_name=theme_name,
                scope_market=scope_market,
                scope_time_window=scope_time_window,
            )
            return  # success
        except (ZhipuClientError, ResearchPersistenceError) as exc:
            last_error = str(exc)
            logger.warning(
                "Serenity run_id=%s attempt %d/%d failed: %s",
                run_id, attempt, max_attempts, exc,
            )
            if attempt >= max_attempts:
                break
            # brief backoff before retry
            time.sleep(2 ** (attempt - 1))
        except Exception as exc:
            last_error = f"unexpected error: {exc}"
            logger.exception(
                "Serenity run_id=%s attempt %d crashed", run_id, attempt,
            )
            break  # don't retry on unexpected errors

    # All attempts exhausted → mark failed
    _mark_failed(db, run_id, theme_id, theme_name, last_error, started)


def _execute_single_attempt(
    db: Session,
    run: ResearchRun,
    theme_id: int,
    theme_name: str,
    scope_market: str,
    scope_time_window: str,
) -> None:
    """One LLM call + persist + complete. Raises on any failure."""
    # 1) Build context
    user_context = build_user_context(theme_name, scope_market, scope_time_window)

    # 2) Call LLM (Q13 triple hard constraint inside ZhipuClient)
    from app.services.llm.zhipu_client import get_zhipu_client
    client = get_zhipu_client()
    result = client.run_serenity_research(user_context=user_context)
    usage = result.pop("_usage", {})

    # 3) Persist to 6 child tables
    persist_research_result(db, run, result)

    # 4) Update run + theme
    run.status = "completed"
    run.llm_token_input = usage.get("token_input", 0)
    run.llm_token_output = usage.get("token_output", 0)
    run.llm_search_count = usage.get("search_count", 0)
    run.completed_at = datetime.utcnow()
    db.flush()

    theme = db.query(ResearchTheme).filter(ResearchTheme.id == theme_id).first()
    if theme:
        theme.last_run_at = run.started_at
        theme.last_run_status = "completed"
        theme.last_run_error = None
    db.commit()

    # 5) Emit completion event (Q17 → NotificationChannel)
    elapsed = time.monotonic() - getattr(_execute_single_attempt, "_started", time.monotonic())
    bus.emit(ResearchRunCompleted(
        run_id=run.id,
        research_theme_id=theme_id,
        research_theme_name=theme_name,
        company_count=len(result.get("company_universe", [])),
        evidence_count=len(result.get("evidence", [])),
        ranking_count=len(result.get("company_ranking", [])),
        token_input=run.llm_token_input,
        token_output=run.llm_token_output,
        elapsed_sec=elapsed,
    ))

    # 6) Q8 monthly budget check (soft limit, alert only)
    _check_monthly_budget(db, run.id)


def _mark_failed(
    db: Session,
    run_id: int,
    theme_id: int,
    theme_name: str,
    error: str,
    started: float,
) -> None:
    run = db.query(ResearchRun).filter(ResearchRun.id == run_id).first()
    if not run:
        return
    run.status = "failed"
    run.error_message = (error or "")[:2000]
    run.completed_at = datetime.utcnow()
    db.flush()

    theme = db.query(ResearchTheme).filter(ResearchTheme.id == theme_id).first()
    if theme:
        theme.last_run_at = run.started_at
        theme.last_run_status = "failed"
        theme.last_run_error = (error or "")[:2000]
    db.commit()

    bus.emit(ResearchRunFailed(
        run_id=run_id,
        research_theme_id=theme_id,
        research_theme_name=theme_name,
        error=error or "unknown error",
        attempt_count=run.attempt_count,
    ))


def _check_monthly_budget(db: Session, triggered_by_run_id: int) -> None:
    """Q8: emit MonthlyBudgetExceeded if current-month spend > budget."""
    from sqlalchemy import func

    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Rough cost estimate: tokens × blended price (input+output average)
    # GLM-4.7: ¥0.005 / 1K tokens (blended). Adjust per model later.
    COST_PER_1K_TOKENS_CNY = 0.005

    row = db.query(
        func.sum(ResearchRun.llm_token_input + ResearchRun.llm_token_output),
    ).filter(
        ResearchRun.status == "completed",
        ResearchRun.started_at >= month_start,
    ).scalar() or 0

    spend_cny = (row or 0) / 1000 * COST_PER_1K_TOKENS_CNY
    budget = SERENITY_RUN_CONFIG["monthly_budget_cny"]
    if spend_cny > budget:
        bus.emit(MonthlyBudgetExceeded(
            month=now.strftime("%Y-%m"),
            spend_cny=round(spend_cny, 2),
            budget_cny=budget,
            triggered_by_run_id=triggered_by_run_id,
        ))
