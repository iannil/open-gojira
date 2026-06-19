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
from app.core.datetime_utils import now

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
from app.core.research_config import COST_PER_1K_TOKENS_CNY, SERENITY_RUN_CONFIG
from app.db.session import SessionLocal
from app.models.research_run import ResearchRun
from app.models.research_theme import ResearchTheme
from app.services.llm.zhipu_client import ZhipuClient, ZhipuClientError
from app.services.research_context_builder import build_user_context
from app.services.research_persistence_service import (
    ResearchPersistenceError,
    persist_research_result,
)
from app.services.search_collector_service import (
    CollectedResult,
    collect_results,
    generate_queries,
    persist_search_results,
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
        elapsed_min = (now() - theme.last_run_at).total_seconds() / 60
        min_gap = SERENITY_RUN_CONFIG["rate_limit_per_theme_minutes"]
        if elapsed_min < min_gap:
            raise ResearchRunnerError(
                f"Theme '{theme.name}' was run {elapsed_min:.1f} minutes ago; "
                f"wait {min_gap - elapsed_min:.1f} more minutes"
            )

    scope_market = market or theme.market
    scope_tw = time_window or "3-12M"

    # llm_provider reflects the model that will actually be called.
    # settings.ZHIPU_MODEL is the source of truth (overridable via .env),
    # SERENITY_RUN_CONFIG["default_model"] is the fallback when unset.
    from app.config import settings
    actual_model = settings.ZHIPU_MODEL or SERENITY_RUN_CONFIG["default_model"]

    run = ResearchRun(
        research_theme_id=theme.id,
        status="running",
        scope_market=scope_market,
        scope_time_window=scope_tw,
        triggered_by=triggered_by,
        llm_provider=actual_model,
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
                started=started,
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
    started: float,
) -> None:
    """One full pipeline: search → LLM synthesis → persist. Raises on failure.

    Path B (2026-06-16): two-step pipeline replaces single chat.completions
    with embedded web_search. Search happens first via standalone API,
    results are persisted + passed to LLM as constrained context.
    """
    # 1) Build context (Lixinger candidates hint)
    user_context = build_user_context(theme_name, scope_market, scope_time_window)

    # 2) Path B step 1: collect real search results
    candidates = _extract_candidates_hint(user_context)
    queries = generate_queries(theme_name, candidates)
    collected = collect_results(queries)
    search_rows_inserted = persist_search_results(db, run.id, collected)
    db.flush()
    logger.info(
        "Serenity run_id=%s collected %d search results from %d queries",
        run.id, search_rows_inserted, len(queries),
    )

    # 3) Path B step 2: LLM synthesis with constrained evidence URLs
    from app.services.llm.zhipu_client import get_zhipu_client
    client = get_zhipu_client()
    search_dicts = [r.model_dump() for r in collected]
    result = client.run_serenity_research(
        user_context=user_context,
        search_results=search_dicts,
    )
    usage = result.pop("_usage", {})

    # 3.5) Persist full LLM interaction log for audit/debugging
    _dump_llm_log(run.id, theme_name, scope_market, user_context, result, usage)

    # 4) Persist structured research to 6 child tables
    persist_research_result(db, run, result)

    # 5) Update run + theme
    run.status = "completed"
    run.llm_token_input = usage.get("token_input", 0)
    run.llm_token_output = usage.get("token_output", 0)
    run.llm_search_count = usage.get("search_count", 0)
    run.completed_at = now()
    db.flush()

    theme = db.query(ResearchTheme).filter(ResearchTheme.id == theme_id).first()
    if theme:
        theme.last_run_at = run.started_at
        theme.last_run_status = "completed"
        theme.last_run_error = None
    db.commit()

    # 5) Emit completion event (Q17 → NotificationChannel)
    elapsed = time.monotonic() - started
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
    run.completed_at = now()
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


def _extract_candidates_hint(user_context: str) -> list[dict]:
    """Parse candidates_hint from build_user_context() output.

    user_context is JSON. candidates_hint is a list of {code, name, industry}.
    Returns [] on parse failure — search_collector will use fallback queries.
    """
    import json
    try:
        data = json.loads(user_context)
        hint = data.get("candidates_hint") if isinstance(data, dict) else None
        if isinstance(hint, list):
            # Normalize keys: research_context_builder emits {code, name, industry}
            return [
                {
                    "code": c.get("code") or c.get("stock_code") or "",
                    "name": c.get("name") or "",
                    "industry": c.get("industry") or "",
                }
                for c in hint
                if isinstance(c, dict)
            ]
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def _check_monthly_budget(db: Session, triggered_by_run_id: int) -> None:
    """Q8: emit MonthlyBudgetExceeded if current-month spend > budget."""
    from sqlalchemy import func

    now_dt = now()
    month_start = now_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Rough cost estimate: tokens × blended price (input+output average)
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
            month=now_dt.strftime("%Y-%m"),
            spend_cny=round(spend_cny, 2),
            budget_cny=budget,
            triggered_by_run_id=triggered_by_run_id,
        ))


def _dump_llm_log(
    run_id: int,
    theme_name: str,
    market: str,
    user_context: str,
    result: dict,
    usage: dict,
) -> None:
    """Persist full LLM interaction log for audit/debugging.

    Writes to `<DATA_DIR>/llm_logs/{run_id}.json` (absolute path from
    settings, immune to CWD). Best-effort — failures logged but do not
    abort the run.
    """
    import json
    from pathlib import Path

    try:
        from app.config import DATA_DIR
        log_dir = DATA_DIR / "llm_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"{run_id}.json"
        payload = {
            "run_id": run_id,
            "theme_name": theme_name,
            "market": market,
            "user_context": user_context[:5000],  # cap to keep file size sane
            "llm_result_summary": {
                "system_change": result.get("system_change", "")[:500],
                "company_count": len(result.get("company_universe", [])),
                "evidence_count": len(result.get("evidence", [])),
                "ranking_count": len(result.get("company_ranking", [])),
            },
            "usage": usage,
            "dumped_at": now().isoformat(),
        }
        log_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        logger.exception("LLM log dump failed for run_id=%s", run_id)
