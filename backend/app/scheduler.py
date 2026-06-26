"""APScheduler integration for periodic data ingestion + alert evaluation.

Jobs:
  - daily_snapshot_job: build a ValuationSnapshot for every watchlist code (trading days, 17:00).
  - daily_kline_sync_job: incremental K-line pull for watchlist + held codes (trading days, 17:15).
  - alert_evaluation_job: evaluate all enabled alert rules (trading days, 17:30).
  - monthly_dividend_sync_job: refresh historical dividend records (1st of month, 03:00).
  - quarterly_financials_refresh_job: refresh annual+quarterly statements during reporting windows.
  - quarterly_shareholders_refresh_job: refresh top-10 / shareholder-count.

The scheduler is disabled by default (SCHEDULER_ENABLED env). All jobs can also be
triggered on demand from the API for testing.

Job cron expressions and enabled state are stored in the `scheduler_jobs` table
and loaded at startup. Changes via API hot-update the running scheduler.
"""
from app.core.datetime_utils import now

import json
import logging
import threading
from datetime import date, datetime, timezone
from functools import wraps
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

from app.config import settings
from app.core.observability import (
    get_logger as _get_obs_logger,
    _generate_id as _obs_gen_id,
    set_trace_id as _obs_set_trace_id,
    _emit_obs_log,
)
from app.db.session import SessionLocal
from app.models.scheduler_config import SchedulerJob
from app.models.valuation import ValuationSnapshot
from app.services import (
    alert_service,
)
from app.services.dividend_service import fetch_and_store_from_lixinger
from app.services.financial_service import fetch_and_store_financials
from app.services.kline_service import get_klines
from app.services.lixinger_client import LixingerError, get_lixinger_client
from app.services.scheduler_config_service import (
    cron_to_trigger,
    ensure_defaults,
    record_finish,
    record_start,
)
from app.services.stocks_detail_service import get_majority_shareholders, get_shareholders_num

logger = logging.getLogger(__name__)

_scheduler: Optional[BackgroundScheduler] = None

# Concurrency protection for manual job triggers
_running_jobs_lock = threading.Lock()
_running_jobs: set[str] = set()


def _utcnow() -> datetime:
    return now()


# ── Execution tracking wrapper ────────────────────────────────────────────


def _with_tracking(job_id: str, func):
    """Wrap a job function to record start/finish in JobExecution table.

    S3.5 — on failure, also emits a critical system_alert (category=scheduler)
    via ``scheduler_alerting.emit_job_failure_alert``. Deduplicated within a
    10-minute window so a chronically failing job doesn't drown the feed.
    """
    from app.services.scheduler_alerting import emit_job_failure_alert

    @wraps(func)
    def wrapper():
        # Assign a dedicated trace_id for the entire job execution
        trace_id = _obs_gen_id()
        _obs_set_trace_id(trace_id)

        db = SessionLocal()
        try:
            exec_ = record_start(db, job_id)
            db.commit()

            sid = _obs_gen_id()
            job_start = {
                "span_id": sid,
                "job_id": job_id,
            }
            obs_log = _get_obs_logger("gojira.scheduler")
            obs_log.info("Job_Start", **job_start)
            _emit_obs_log({"event": "Job_Start", **job_start})

            result = func()

            record_finish(
                db,
                exec_.id,
                "success",
                result_summary=json.dumps(result, default=str, ensure_ascii=False),
            )
            db.commit()

            job_end = {
                "span_id": sid,
                "job_id": job_id,
                "status": "success",
                "result_summary": json.dumps(result, default=str, ensure_ascii=False)[:500],
            }
            obs_log.info("Job_End", **job_end)
            _emit_obs_log({"event": "Job_End", **job_end})

            return result
        except Exception as e:
            try:
                record_finish(db, exec_.id, "failed", error_message=str(e))
                db.commit()
            except Exception:
                logger.exception("failed to record job execution error")

            # S3.5 — surface the failure as a system_alert so the UI can
            # show a red banner. Dedup is handled inside the helper.
            try:
                emit_job_failure_alert(db, job_id=job_id, error=e)
                db.commit()
            except Exception:
                logger.exception(
                    "failed to emit scheduler alert for job_id=%s", job_id,
                )

            error_event = {
                "job_id": job_id,
                "error_type": type(e).__name__,
                "error_message": str(e)[:1000],
            }
            obs_log = _get_obs_logger("gojira.scheduler")
            obs_log.error("Job_Error", **error_event)
            _emit_obs_log({"event": "Job_Error", **error_event})
            raise
        finally:
            db.close()
    return wrapper


# ── Jobs ──────────────────────────────────────────────────────────────────


def daily_universe_bootstrap_job() -> dict:
    """Sync the full A-share stock list: detect new listings and delistings."""
    from app.services.pipelines.manager import PipelineManager

    with SessionLocal() as db:
        mgr = PipelineManager(db)
        result = mgr.start(
            pipeline_type="universe_bootstrap",
            stock_codes=[],
            background=False,
        )
        return result


def daily_base_sync_job() -> dict:
    """Base tier sync: valuation data for all A-shares."""
    from app.services.data_management_service import get_all_active_stock_codes
    from app.services.pipelines.manager import PipelineManager

    with SessionLocal() as db:
        all_codes = get_all_active_stock_codes(db)
        if not all_codes:
            logger.info("daily_base_sync_job: no stocks in master list, skipping")
            return {"synced": 0, "codes": 0}
        mgr = PipelineManager(db)
        result = mgr.start(
            pipeline_type="valuations",
            stock_codes=all_codes,
            background=False,
        )
        return result


def daily_deep_sync_job() -> dict:
    """Deep sync: financials, klines, dividends for candidates."""
    from app.services.deep_sync_service import sync_candidates_deep_data

    with SessionLocal() as db:
        return sync_candidates_deep_data(db)


def daily_snapshot_job() -> dict:
    """Fetch realtime fundamentals for every watched code, persist snapshots."""
    with SessionLocal() as db:
        codes = watchlist_service.all_watched_codes(db)
        if not codes:
            logger.info("daily_snapshot_job: no watchlist items, skipping")
            return {"snapshots": 0, "codes": 0}

        try:
            client = get_lixinger_client()
            data = client.get_fundamentals(
                stock_codes=codes,
                metrics=[
                    "pe_ttm", "pb", "dyr", "sp",
                    "pe_ttm.y10.cvpos", "pb.y10.cvpos",
                ],
            )
        except LixingerError:
            logger.exception("daily_snapshot_job: lixinger failure")
            return {"snapshots": 0, "codes": len(codes), "error": "lixinger"}

        today = date.today()
        count = 0
        for item in data:
            code = item.get("stockCode")
            if not code:
                continue
            existing = (
                db.query(ValuationSnapshot)
                .filter(ValuationSnapshot.stock_code == code, ValuationSnapshot.date == today)
                .first()
            )
            pe_pct = _extract_pct(item.get("pe_ttm.y10.cvpos"))
            pb_pct = _extract_pct(item.get("pb.y10.cvpos"))
            if existing:
                existing.pe_ttm = item.get("pe_ttm")
                existing.pb = item.get("pb")
                existing.pe_percentile_10y = pe_pct
                existing.pb_percentile_10y = pb_pct
                existing.dividend_yield = item.get("dyr")
            else:
                db.add(
                    ValuationSnapshot(
                        stock_code=code,
                        date=today,
                        pe_ttm=item.get("pe_ttm"),
                        pb=item.get("pb"),
                        pe_percentile_10y=pe_pct,
                        pb_percentile_10y=pb_pct,
                        dividend_yield=item.get("dyr"),
                    )
                )
                count += 1
        db.commit()
        logger.info("daily_snapshot_job: inserted %d / %d codes", count, len(codes))
        return {"snapshots": count, "codes": len(codes)}


def alert_evaluation_job() -> dict:
    """Evaluate all enabled alert rules."""
    with SessionLocal() as db:
        result = alert_service.evaluate_all_rules(db)
        logger.info("alert_evaluation_job: %s", result)
        return result


def thesis_evaluation_job() -> dict:
    """v2 Phase 2 #9 阶段 B: run both thesis monitor checks.

    Independent from alert_evaluation_job (which is for AlertRule-based
    price/financial alerts). This job handles:
      - check_held_stocks: thesis_variables_json breaches (sync'd vars)
      - check_claim_variables: research_claim_variables breaches (LLM-proposed)
    """
    from app.services.thesis_monitor_service import (
        check_claim_variables, check_held_stocks,
    )
    with SessionLocal() as db:
        # Existing thesis_variables_json checks (silent — just returns alerts)
        legacy_alerts = check_held_stocks(db)
        # New claim_variables checks (emit ThesisAlertTriggered per breach)
        summary = check_claim_variables(db)
        result = {
            "legacy_alerts": len(legacy_alerts),
            "checked": summary.checked,
            "breached": summary.breached,
            "suppressed": summary.suppressed,
            "skipped_no_data": summary.skipped_no_data,
            "failed": summary.failed,
        }
        logger.info("thesis_evaluation_job: %s", result)
        return result


# ── Phase F: extended sync jobs ───────────────────────────────────────────


def _watched_and_held_codes(db: Session) -> list[str]:
    """Codes the user actively cares about: watchlist + open holdings."""
    from app.services import position_service

    watch = set(watchlist_service.all_watched_codes(db))
    return sorted(watch | position_service.held_stock_codes(db))


def daily_kline_sync_job() -> dict:
    """Incrementally pull daily K-line for watchlist + held codes."""
    with SessionLocal() as db:
        codes = _watched_and_held_codes(db)
        ok = 0
        for code in codes:
            try:
                get_klines(db, code, refresh=True)
                ok += 1
            except Exception:
                logger.exception("daily_kline_sync_job: failed for %s", code)
        logger.info("daily_kline_sync_job: synced %d / %d", ok, len(codes))
        return {"synced": ok, "codes": len(codes)}


def _watched_held_and_candidate_codes(db: Session) -> list[str]:
    """Codes the user actively cares about + current plan candidates.

    Extends _watched_and_held_codes with active Candidate stocks —
    needed so prev_close is fresh for price validation on candidate
    promotions to drafts.
    """
    base = set(_watched_and_held_codes(db))
    from app.models.candidate import Candidate
    candidates = {
        c.stock_code
        for c in db.query(Candidate).filter(Candidate.status == "active").all()
    }
    return sorted(base | candidates)


def daily_prev_close_sync_job() -> dict:
    """Refresh prev_close for held + watched + candidate stocks.

    Must run AFTER daily_kline_sync (17:15) so the latest K-line is
    already cached. prev_close is the reference price for 涨跌停
    (price band) validation in trade_service.

    Scope is intentionally narrow (held/watched/candidate, NOT full
    market) — full-market sync would burn ~5625 Lixinger calls/day
    for a field only needed at order-draft time.
    """
    from app.services.kline_service import update_prev_close_batch
    with SessionLocal() as db:
        codes = _watched_held_and_candidate_codes(db)
        if not codes:
            logger.info("daily_prev_close_sync_job: no codes to sync, skipping")
            return {"synced": 0, "codes": 0}
        count = update_prev_close_batch(db, codes)
        logger.info("daily_prev_close_sync_job: synced %d / %d", count, len(codes))
        return {"synced": count, "codes": len(codes)}


def intraday_monitor_job() -> dict:
    """盘中监控 (retired 2026-06-26):唯一用途是 stop_profit 止盈告警,已随
    decision 2-A 退役 (止盈改由 sell_trigger 处理)。保留空壳以兼容旧注册名。
    """
    return {"checked": 0, "alerts": 0}


def monthly_dividend_sync_job() -> dict:
    """Refresh historical dividend records for watchlist + held codes."""
    with SessionLocal() as db:
        codes = _watched_and_held_codes(db)
        total_inserted = 0
        ok = 0
        for code in codes:
            try:
                total_inserted += fetch_and_store_from_lixinger(db, code, years=10)
                ok += 1
            except Exception:
                logger.exception("monthly_dividend_sync_job: failed for %s", code)
        logger.info("monthly_dividend_sync_job: %d new records across %d / %d codes",
                    total_inserted, ok, len(codes))
        return {"inserted": total_inserted, "codes": len(codes), "ok": ok}


def quarterly_financials_refresh_job() -> dict:
    """Quarterly financials refresh tied to the A-share reporting window
    (annual report Mar-Apr, semi-annual Aug, Q3 Oct). This is the single
    canonical financials refresh — the previous weekly variant was dropped
    because it issued the same Lixinger calls 4× more often without ever
    catching net-new data outside reporting windows.
    """
    with SessionLocal() as db:
        codes = _watched_and_held_codes(db)
        ok = 0
        for code in codes:
            try:
                fetch_and_store_financials(db, code, years=5)
                ok += 1
            except Exception:
                logger.exception("quarterly_financials_refresh_job: failed for %s", code)
        logger.info("quarterly_financials_refresh_job: refreshed %d / %d", ok, len(codes))
        return {"refreshed": ok, "codes": len(codes)}


def quarterly_shareholders_refresh_job() -> dict:
    """Refresh majority shareholders + shareholder-count for watched codes."""
    with SessionLocal() as db:
        codes = _watched_and_held_codes(db)
        ok = 0
        for code in codes:
            try:
                get_majority_shareholders(code)
                get_shareholders_num(code)
                ok += 1
            except Exception:
                logger.exception("quarterly_shareholders_refresh_job: failed for %s", code)
        logger.info("quarterly_shareholders_refresh_job: refreshed %d / %d", ok, len(codes))
        return {"refreshed": ok, "codes": len(codes)}


# ── Helpers ───────────────────────────────────────────────────────────────


def _extract_pct(raw) -> Optional[float]:
    if raw is None:
        return None
    val = raw.get("cvpos") if isinstance(raw, dict) else raw
    if val is None:
        return None
    val = float(val)
    return val * 100.0 if val <= 1.0 else val


def daily_plan_evaluation_job() -> dict:
    """Run all active plans: screening + optional trading evaluation."""

    from app.services import plan_runner

    with SessionLocal() as db:
        results = plan_runner.run_all_active(db)
        db.commit()
        return {
            "evaluated": len(results),
            "scanned": sum(r.scanned for r in results),
            "passed": sum(r.passed for r in results),
            "drafts_emitted": sum(r.drafts_emitted for r in results),
            "errors": sum(len(r.errors) for r in results),
        }


def _weekly_rebalancing_review(db: Session) -> None:
    """Weekly rebalancing review — creates alerts for significant drift.

    Checks position, quadrant, and theme weights against targets and creates
    alert events for any drift exceeding 10% (high priority).
    """
    from app.services import rebalance_service

    result = rebalance_service.generate_rebalancing_alerts(db, drift_threshold=0.05)

    high_count = result["high_priority"]
    if high_count > 0:
        from app.services.alert_service import _emit

        class _SyntheticRule:
            id = -1
            stock_code = None
            rule_type = "weekly_rebalancing_review"

        rule = _SyntheticRule()

        suggestions = result.get("suggestions", [])
        high_suggestions = [s for s in suggestions if s.get("priority") == "high"]

        details = []
        for s in high_suggestions[:5]:
            if s["level"] == "position":
                details.append(
                    f"{s['code']}: 当前{s['current_pct']*100:.1f}%, "
                    f"目标{s['target_pct']*100:.1f}%, "
                    f"漂移{s['drift_pct']*100:+.1f}% ({s['action']})"
                )
            elif s["level"] == "quadrant":
                details.append(
                    f"{s['quadrant']}: 当前{s['current_pct']*100:.1f}%, "
                    f"目标{s['target_pct']*100:.1f}%, "
                    f"漂移{s['drift_pct']*100:+.1f}% ({s['action']})"
                )
            elif s["level"] == "theme":
                details.append(
                    f"{s['theme']}: 当前{s['current_pct']*100:.1f}%, "
                    f"目标{s['target_pct']*100:.1f}%, "
                    f"漂移{s['drift_pct']*100:+.1f}% ({s['action']})"
                )

        detail_text = "; ".join(details)
        if len(high_suggestions) > 5:
            detail_text += f"... (共{high_count}项高优先级漂移)"

        _emit(
            db,
            rule,
            title=f"周度再平衡检查: 发现{high_count}项高优先级漂移",
            detail=detail_text,
            payload=result,
            severity="alert",
        )
        logger.info(
            "weekly_rebalancing_review: %d high-priority drifts detected",
            high_count,
        )
    else:
        logger.info("weekly_rebalancing_review: no significant drifts")


def weekly_rebalancing_review_job() -> dict:
    """Scheduler entry point for weekly rebalancing review."""
    with SessionLocal() as db:
        _weekly_rebalancing_review(db)
        db.commit()
        return {"status": "completed"}


def daily_cycle_assessment_job() -> dict:
    """Fetch CSI300 PE/PB history and compute market cycle position."""
    from app.services.cycle_assessment_service import assess_cycle

    with SessionLocal() as db:
        assessment = assess_cycle(db)
        logger.info(
            "daily_cycle_assessment_job: position=%s, pe_pct=%s",
            assessment.cycle_position,
            assessment.pe_pct_10y,
        )
        return assessment.to_dict()


def _monthly_thesis_variable_sync_job() -> dict:
    """Sync thesis variables from stored financial data for held stocks."""
    from app.services.thesis_variable_sync_service import sync_all_held

    with SessionLocal() as db:
        result = sync_all_held(db)
    logger.info("monthly_thesis_variable_sync_job: %s", result)
    return result


def _weekly_research_refresh_job() -> dict:
    """Serenity research weekly auto-refresh (Q6 D trigger).

    Q12: skips themes with last_run_status='failed' to avoid burning tokens.
    """
    from app.services.research_scheduler_service import run_due_research_themes

    result = run_due_research_themes()
    logger.info("weekly_research_refresh_job: %s", result)
    return result


def weekly_business_pattern_inference_job() -> dict:
    """C3: weekly batch re-inference of Stock.business_pattern_id.

    Skips user-overridden stocks (inferred_at IS NULL + id NOT NULL).
    Catches stocks synced after the last inference run, plus industry
    string changes that weren't caught by the per-sync hook.
    """
    from app.services.business_pattern_service import infer_all_stocks

    with SessionLocal() as db:
        result = infer_all_stocks(db, force=False)
    logger.info("weekly_business_pattern_inference_job: %s", result)
    return result


# ── Phase S4A: corporate action pipeline ──────────────────────────────────


def weekly_dividend_sync_job() -> dict:
    """Weekly pull of Lixinger dividend history for held/watched/candidate stocks.

    The dividend endpoint returns cash + stock dividends + capitalization
    in one record per ex-date; sync_service splits these into one
    CorpAction row per action_type. Existing rows are skipped (unique
    constraint on (stock_code, ex_date, action_type, source)).

    Weekly cadence balances freshness against Lixinger call volume:
    the daily_apply job consumes these rows on the morning of the
    ex-date, so a one-week window is plenty of headroom.
    """
    from app.services.corp_action_sync_service import sync_dividends_batch

    with SessionLocal() as db:
        codes = _watched_held_and_candidate_codes(db)
        if not codes:
            logger.info("weekly_dividend_sync_job: no codes, skipping")
            return {"synced": 0, "codes": 0}
        new = sync_dividends_batch(db, codes)
        logger.info(
            "weekly_dividend_sync_job: %d new corp_actions across %d codes",
            new, len(codes),
        )
        return {"new_count": new, "codes": len(codes)}


def daily_corp_action_apply_job() -> dict:
    """Apply pending corp_actions whose ex_date <= today (trading days).

    Runs at 09:00 every weekday. On non-trading days there are usually
    no ex-dates either, but to be safe we apply any pending backlog
    regardless of trading-day status (idempotent — applied rows are
    skipped on the next run).

    `as_of=today` ensures we never apply an action whose ex_date is in
    the future (those stay in pending until the morning they take effect).
    """
    from app.services.corp_action_processor_service import (
        process_pending_corp_actions,
    )

    with SessionLocal() as db:
        count = process_pending_corp_actions(db, as_of=date.today())
        if count > 0:
            logger.info("daily_corp_action_apply_job: applied %d", count)
        db.commit()
        return {"applied_count": count}


# ── Phase S5: intraday price polling ──────────────────────────────────────


def intraday_price_poll_job() -> dict:
    """Poll realtime prices every 5 min during A-share trading hours.

    Guards:
      1. ``is_trading_day()`` — skips weekends + holidays (S5.1)
      2. Local-time hour check — only runs 9:00-11:30 + 13:00-15:00
         (skips the 12:00-13:00 lunch break + outside sessions)

    Pipeline (delegates to S5.3 services):
      - ``intraday_watch_list`` — union of held + watched + drafts + candidates
      - ``get_realtime_prices`` — one batched Sina call
      - ``check_holding`` — per-position stop-loss / take-profit
      - ``dispatch_alert`` — pushes any new alerts to notification channels

    Returns a summary dict consumed by the tracking wrapper.
    """
    from datetime import datetime as _dt

    from sqlalchemy import select

    from app.models.system_alert import SystemAlert
    from app.services.intraday_monitor_service import poll_once
    from app.services.notification_service import dispatch_alert
    from app.services.trading_calendar_service import is_trading_day

    with SessionLocal() as db:
        # Guard 1: trading day
        if not is_trading_day(db, date.today()):
            logger.info("intraday_price_poll: non-trading day, skipping")
            return {"skipped": "non_trading_day"}

        # Guard 2: trading hours (local time, Asia/Shanghai)
        # 9:30-11:30 morning, 13:00-15:00 afternoon. Skip lunch (12:xx).
        now = _dt.now()
        hour_min = now.hour * 100 + now.minute
        in_morning = 930 <= hour_min <= 1130
        in_afternoon = 1300 <= hour_min <= 1500
        if not (in_morning or in_afternoon):
            logger.info(
                "intraday_price_poll: outside trading hours (now=%s), skipping",
                now.strftime("%H:%M"),
            )
            return {"skipped": "outside_trading_hours"}

        # Poll: fetch + check rules + emit alerts (poll_once commits)
        result = poll_once(db)

        # Dispatch alerts created in the last 5 minutes. poll_once creates
        # them via stop_loss_service._trigger → system_alert_service.
        from datetime import timedelta

        cutoff = _utcnow() - timedelta(minutes=5)
        recent_alerts = list(
            db.execute(
                select(SystemAlert).where(
                    SystemAlert.created_at >= cutoff,
                    SystemAlert.resolved_at.is_(None),
                )
            ).scalars().all()
        )
        dispatched = 0
        for alert in recent_alerts:
            try:
                dispatch_alert(db, alert)
                dispatched += 1
            except Exception as e:
                logger.warning(
                    "Dispatch failed for alert %s: %s", alert.id, e
                )
        db.commit()

        summary = {
            "codes_checked": result.codes_checked,
            "prices_fetched": result.prices_fetched,
            "stop_loss_events": len(result.stop_loss_events),
            "take_profit_events": len(result.take_profit_events),
            "errors": len(result.errors),
            "dispatched_alerts": dispatched,
        }
        logger.info("intraday_price_poll: %s", summary)
        return summary


def pipeline_stale_sweep_job() -> dict:
    """F15 (2026-06-18): periodic sweep for stuck pipeline runs.

    Background threads can die silently (OOM, network hang, code bug) while
    pipeline_runs.status stays at 'running'. recover_stale_runs on startup
    handles process restarts; this job handles in-process thread death.

    L5 fix (2026-06-19): thresholds raised from 30min/2h → 6h/8h. The
    original 30min was right for short pipelines (valuations ~60s) but
    misclassified long-running backfills (financials 5626 stocks × 9 quarters
    ≈ 2-3h) as stuck. Backfill progress is hard to detect via updated_at
    because SQLAlchemy onupdate=func.now() fires on UPDATE only, and pipeline
    rows are rarely updated mid-run.

    6h/8h: safe upper bound. Real stuck threads will be cleaned within 8h
    instead of 2h, but backfill of 5626 stocks finishes well under 6h.
    """
    from app.services.pipelines.manager import PipelineManager

    with SessionLocal() as db:
        from datetime import timedelta
        from app.models.pipeline import PipelineRun
        from sqlalchemy import select

        threshold = _utcnow() - timedelta(hours=6)
        stale_statuses = ("running", "pending")
        hard_threshold = _utcnow() - timedelta(hours=8)
        result = db.execute(
            select(PipelineRun).where(
                PipelineRun.status.in_(stale_statuses),
            )
        ).scalars().all()
        recovered = []
        for run in result:
            updated = run.updated_at or run.started_at
            if updated is None or updated < hard_threshold:
                # Definitely dead — older than 8h with no progress
                run.status = "failed"
                if not run.finished_at:
                    run.finished_at = _utcnow()
                recovered.append(run.id)
            elif updated < threshold:
                # Possibly dead — no progress in 6h+
                run.status = "failed"
                if not run.finished_at:
                    run.finished_at = _utcnow()
                recovered.append(run.id)
        if recovered:
            db.commit()
        logger.info(
            "pipeline_stale_sweep: recovered %d stuck runs %s",
            len(recovered), recovered[:5],
        )
        return {"recovered": len(recovered), "ids": recovered}


def research_stale_sweep_job() -> dict:
    """F23 (2026-06-18): periodic sweep for stuck serenity research runs.

    Serenity worker thread can hang on GLM API call (memory
    feedback-glm-connection-hang: SSL read blocks, httpx timeout ineffective).
    The thread doesn't crash so the run stays 'running' forever.

    Threshold: 15 min soft (likely dead), 30 min hard (definitely dead).
    Typical serenity run = 5 min; 15 min = 3× safety margin.
    """
    from datetime import timedelta
    from app.models.research_run import ResearchRun
    from sqlalchemy import select

    with SessionLocal() as db:
        soft_threshold = _utcnow() - timedelta(minutes=15)
        hard_threshold = _utcnow() - timedelta(minutes=30)

        stuck = db.execute(
            select(ResearchRun).where(ResearchRun.status == "running")
        ).scalars().all()
        recovered = []
        for run in stuck:
            if run.started_at is None:
                continue
            if run.started_at < hard_threshold:
                run.status = "failed"
                run.error_message = (
                    "Worker hung > 30 min (GLM SSL read blocked, "
                    "per feedback-glm-connection-hang)"
                )
                if not run.completed_at:
                    run.completed_at = _utcnow()
                recovered.append(run.id)
            elif run.started_at < soft_threshold:
                run.status = "failed"
                run.error_message = "Worker hung > 15 min (likely GLM connection issue)"
                if not run.completed_at:
                    run.completed_at = _utcnow()
                recovered.append(run.id)

        if recovered:
            db.commit()
            # Sync theme last_run_status
            from app.models.research_theme import ResearchTheme
            for run_id in recovered:
                run_obj = db.get(ResearchRun, run_id)
                if run_obj:
                    theme = db.get(ResearchTheme, run_obj.research_theme_id)
                    if theme:
                        theme.last_run_status = "failed"
                        theme.last_run_error = run_obj.error_message
            db.commit()
        logger.info(
            "research_stale_sweep: recovered %d stuck runs %s",
            len(recovered), recovered[:5],
        )
        return {"recovered": len(recovered), "ids": recovered}


# ── v2 LLM Pipeline jobs (2026-06-24) ─────────────────────────────────────


def v2_quality_screen_job() -> dict:
    """v2: weekly quality_screen on full universe → watchlist."""
    from app.services.pipelines.llm import quality_screen_pipeline
    with SessionLocal() as db:
        try:
            summary = quality_screen_pipeline.screen_universe(db, limit=200)
            db.commit()
            logger.info("v2_quality_screen: %s", summary)
            return summary
        except Exception:
            db.rollback()
            logger.exception("v2_quality_screen_job failed")
            return {"error": str(Exception)}


def v2_deep_research_job() -> dict:
    """v2: weekly deep_research on top 10 watchlist stocks.

    Per decision 7: weekly cadence, 30-day cache window per stock.
    """
    from app.services.pipelines.llm import deep_research_pipeline
    from app.models.stock_lifecycle import StockLifecycle
    from app.services import lifecycle_service

    with SessionLocal() as db:
        try:
            # Pick top 10 watchlist stocks needing research
            candidates = (
                db.query(StockLifecycle.stock_code)
                .filter(StockLifecycle.current_state == "watchlist")
                .order_by(StockLifecycle.entered_state_at.desc())
                .limit(10)
                .all()
            )
            codes = [c[0] for c in candidates]
            results = {"attempted": len(codes), "completed": 0, "skipped_cache": 0, "failed": 0}
            for code in codes:
                if not lifecycle_service.needs_research(db, code, cache_days=30):
                    results["skipped_cache"] += 1
                    continue
                try:
                    deep_research_pipeline.run(code, db_session=db)
                    db.commit()
                    results["completed"] += 1
                except Exception:
                    db.rollback()
                    logger.exception("v2_deep_research failed for %s", code)
                    results["failed"] += 1
            logger.info("v2_deep_research: %s", results)
            return results
        except Exception:
            logger.exception("v2_deep_research_job failed")
            return {"error": "see logs"}


def v2_thesis_tracker_job() -> dict:
    """v2: weekly thesis_tracker on all active holdings."""
    from app.services.pipelines.llm import thesis_tracker_pipeline
    from app.services import position_service

    with SessionLocal() as db:
        try:
            codes = sorted(position_service.held_stock_codes(db))
            results = {"attempted": len(codes), "completed": 0, "failed": 0}
            for code in codes:
                try:
                    thesis_tracker_pipeline.run(code, db_session=db)
                    db.commit()
                    results["completed"] += 1
                except Exception:
                    db.rollback()
                    logger.exception("v2_thesis_tracker failed for %s", code)
                    results["failed"] += 1
            logger.info("v2_thesis_tracker: %s", results)
            return results
        except Exception:
            logger.exception("v2_thesis_tracker_job failed")
            return {"error": "see logs"}


def daily_draft_generation_job() -> dict:
    """Phase 5 (decision 9/10): generate BUY drafts from fresh BUY research
    reports whose price entered a buy tier (激进/稳健) + portfolio has space;
    cancel expired drafts (TTL 7d)."""
    from app.services import draft_generator

    with SessionLocal() as db:
        try:
            result = draft_generator.generate_buy_drafts(db)
            db.commit()
            logger.info(
                "daily_draft_generation: generated=%s expired=%s scanned=%s",
                result["generated"], result["expired_cancelled"], result["scanned"],
            )
            return result
        except Exception:
            db.rollback()
            logger.exception("daily_draft_generation_job failed")
            return {"error": "see logs"}


# ── Job Registry ──────────────────────────────────────────────────────────

# Maps job_id → unwrapped function (tracking is applied during scheduling)
# v2 (2026-06-24): v1 jobs removed (thesis_evaluation, daily_plan_evaluation,
# weekly_rebalancing_review, daily_cycle_assessment, monthly_thesis_variable_sync,
# weekly_business_pattern_inference, intraday_monitor, weekly_research_refresh,
# research_stale_sweep). Replaced by v2 LLM Pipelines below.
JOB_REGISTRY = {
    "daily_universe_bootstrap": daily_universe_bootstrap_job,
    "daily_base_sync": daily_base_sync_job,
    "daily_deep_sync": daily_deep_sync_job,
    "daily_snapshot": daily_snapshot_job,
    "alert_evaluation": alert_evaluation_job,
    "daily_kline_sync": daily_kline_sync_job,
    "daily_prev_close_sync": daily_prev_close_sync_job,
    "monthly_dividend_sync": monthly_dividend_sync_job,
    "quarterly_financials_refresh": quarterly_financials_refresh_job,
    "quarterly_shareholders_refresh": quarterly_shareholders_refresh_job,
    "weekly_dividend_sync": weekly_dividend_sync_job,
    "daily_corp_action_apply": daily_corp_action_apply_job,
    "intraday_price_poll": intraday_price_poll_job,
    "pipeline_stale_sweep": pipeline_stale_sweep_job,
    "daily_draft_generation": daily_draft_generation_job,
    # v2 LLM Pipelines
    "v2_quality_screen_weekly": v2_quality_screen_job,
    "v2_deep_research_weekly": v2_deep_research_job,
    "v2_thesis_tracker_weekly": v2_thesis_tracker_job,
}


# ── Lifecycle ─────────────────────────────────────────────────────────────


def start_scheduler() -> Optional[BackgroundScheduler]:
    global _scheduler
    if not getattr(settings, "SCHEDULER_ENABLED", False):
        logger.info("Scheduler disabled (SCHEDULER_ENABLED=false)")
        return None
    if _scheduler is not None:
        return _scheduler

    sched = BackgroundScheduler(timezone="Asia/Shanghai")

    # Load config from DB
    db = SessionLocal()
    try:
        ensure_defaults(db)
        db.commit()
        configs = db.query(SchedulerJob).all()
    finally:
        db.close()

    for cfg in configs:
        func = JOB_REGISTRY.get(cfg.job_id)
        if not func:
            logger.warning("start_scheduler: unknown job_id %s in DB, skipping", cfg.job_id)
            continue
        if not cfg.enabled:
            logger.info("start_scheduler: %s is disabled, skipping", cfg.job_id)
            continue
        try:
            trigger = cron_to_trigger(cfg.cron_expr)
        except Exception:
            logger.exception("start_scheduler: invalid cron for %s: %s", cfg.job_id, cfg.cron_expr)
            continue
        sched.add_job(
            _with_tracking(cfg.job_id, func),
            trigger,
            id=cfg.job_id,
            replace_existing=True,
        )

    sched.start()
    _scheduler = sched
    logger.info("Scheduler started with %d jobs", len(sched.get_jobs()))
    return sched


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is None:
        return
    _scheduler.shutdown(wait=True)
    _scheduler = None
    logger.info("Scheduler stopped")


def list_jobs() -> list[dict]:
    """Merge DB config with APScheduler runtime state."""
    db = SessionLocal()
    try:
        configs = {c.job_id: c for c in db.query(SchedulerJob).all()}
    finally:
        db.close()

    runtime_jobs = {}
    if _scheduler is not None:
        for job in _scheduler.get_jobs():
            runtime_jobs[job.id] = {
                "next_run_time": str(job.next_run_time) if job.next_run_time else None,
            }

    from app.services.scheduler_config_service import get_last_execution

    db2 = SessionLocal()
    try:
        out = []
        for job_id, cfg in configs.items():
            last_exec = get_last_execution(db2, job_id)
            runtime = runtime_jobs.get(job_id, {})
            out.append({
                "job_id": job_id,
                "cron_expr": cfg.cron_expr,
                "enabled": cfg.enabled,
                "description": cfg.description,
                "next_run_time": runtime.get("next_run_time"),
                "last_run_at": str(last_exec.started_at) if last_exec and last_exec.started_at else None,
                "last_run_status": last_exec.status if last_exec else None,
                "last_duration_ms": last_exec.duration_ms if last_exec else None,
                "created_at": str(cfg.created_at) if cfg.created_at else None,
                "updated_at": str(cfg.updated_at) if cfg.updated_at else None,
            })
    finally:
        db2.close()
    return out


def run_job_now(job_id: str) -> dict:
    """Execute a registered job synchronously (for manual triggering)."""
    with _running_jobs_lock:
        if job_id in _running_jobs:
            raise ValueError(f"Job {job_id} is already running")
        _running_jobs.add(job_id)

    try:
        func = JOB_REGISTRY.get(job_id)
        if not func:
            raise KeyError(f"Unknown job: {job_id}")

        db = SessionLocal()
        try:
            exec_ = record_start(db, job_id)
            db.commit()
            started = _utcnow()
            result = func()
            record_finish(
                db,
                exec_.id,
                "success",
                result_summary=json.dumps(result, default=str, ensure_ascii=False),
            )
            db.commit()
            return {
                "job": job_id,
                "started_at": str(started),
                "finished_at": str(_utcnow()),
                "result": result,
                "execution_id": exec_.id,
            }
        except Exception as e:
            try:
                record_finish(db, exec_.id, "failed", error_message=str(e))
                db.commit()
            except Exception:
                logger.exception("failed to record manual job error")
            raise
        finally:
            db.close()
    finally:
        with _running_jobs_lock:
            _running_jobs.discard(job_id)


def reschedule_job(job_id: str) -> None:
    """Hot-update a job in the running scheduler based on current DB config."""
    if _scheduler is None:
        return

    db = SessionLocal()
    try:
        cfg = db.query(SchedulerJob).filter(SchedulerJob.job_id == job_id).first()
    finally:
        db.close()

    if not cfg:
        return

    func = JOB_REGISTRY.get(job_id)
    if not func:
        return

    # Remove existing job if present
    try:
        _scheduler.remove_job(job_id)
    except Exception:
        pass

    if cfg.enabled:
        trigger = cron_to_trigger(cfg.cron_expr)
        _scheduler.add_job(
            _with_tracking(job_id, func),
            trigger,
            id=job_id,
            replace_existing=True,
        )
        logger.info("reschedule_job: %s rescheduled with cron=%s", job_id, cfg.cron_expr)
    else:
        logger.info("reschedule_job: %s disabled, removed from scheduler", job_id)
