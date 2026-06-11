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
from app.models.holding import Holding
from app.models.scheduler_config import SchedulerJob
from app.models.valuation import ValuationSnapshot
from app.services import (
    alert_service,
    watchlist_service,
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
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── Execution tracking wrapper ────────────────────────────────────────────


def _with_tracking(job_id: str, func):
    """Wrap a job function to record start/finish in JobExecution table."""
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


# ── Phase F: extended sync jobs ───────────────────────────────────────────


def _watched_and_held_codes(db: Session) -> list[str]:
    """Codes the user actively cares about: watchlist + open holdings."""
    watch = set(watchlist_service.all_watched_codes(db))
    holdings = {h.stock_code for h in db.query(Holding).filter(Holding.sell_date.is_(None)).all()}
    return sorted(watch | holdings)


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


def intraday_monitor_job() -> dict:
    """盘中监控：每 5 分钟检查 watchlist 股票价格，触发止盈告警。

    默认关闭，需通过 API 启用。
    """
    with SessionLocal() as db:
        codes = _watched_and_held_codes(db)
        if not codes:
            return {"checked": 0, "alerts": 0}

        from app.services.alert_service import (
            list_rules, _fetch_realtime,
            _eval_stop_profit, _should_dedupe,
        )

        stop_profit_rules = [
            r for r in list_rules(db, enabled_only=True)
            if r.rule_type == "stop_profit"
        ]
        if not stop_profit_rules:
            return {"checked": len(codes), "alerts": 0}

        realtime = _fetch_realtime([r.stock_code for r in stop_profit_rules if r.stock_code])
        alerts = 0
        for rule in stop_profit_rules:
            if _should_dedupe(db, rule):
                continue
            snapshot = realtime.get(rule.stock_code) if rule.stock_code else None
            ev = _eval_stop_profit(db, rule, snapshot)
            if ev:
                alerts += 1
        db.commit()
        return {"checked": len(codes), "alerts": alerts}


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


# ── Job Registry ──────────────────────────────────────────────────────────

# Maps job_id → unwrapped function (tracking is applied during scheduling)
JOB_REGISTRY = {
    "daily_universe_bootstrap": daily_universe_bootstrap_job,
    "daily_base_sync": daily_base_sync_job,
    "daily_deep_sync": daily_deep_sync_job,
    "daily_snapshot": daily_snapshot_job,
    "daily_cycle_assessment": daily_cycle_assessment_job,
    "alert_evaluation": alert_evaluation_job,
    "daily_kline_sync": daily_kline_sync_job,
    "monthly_dividend_sync": monthly_dividend_sync_job,
    "quarterly_financials_refresh": quarterly_financials_refresh_job,
    "quarterly_shareholders_refresh": quarterly_shareholders_refresh_job,
    "daily_plan_evaluation": daily_plan_evaluation_job,
    "weekly_rebalancing_review": weekly_rebalancing_review_job,
    "monthly_thesis_variable_sync": _monthly_thesis_variable_sync_job,
    "intraday_monitor": intraday_monitor_job,
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
