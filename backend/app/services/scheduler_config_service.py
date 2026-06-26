"""Scheduler configuration and execution tracking service."""

import logging
from datetime import datetime, timezone

from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

from app.models.scheduler_config import JobExecution, SchedulerJob
from app.core.datetime_utils import now

logger = logging.getLogger(__name__)

# Default job configs — matches JOB_REGISTRY in scheduler.py
DEFAULT_JOBS: dict[str, dict] = {
    "daily_universe_bootstrap": {
        "cron_expr": "0 15 * * 1-5",
        "description": "全A股列表增量同步（新股/退市检测）",
    },
    "daily_base_sync": {
        "cron_expr": "15 15 * * 1-5",
        "description": "全量基础估值同步（PE/PB/股息率/百分位）",
    },
    "daily_snapshot": {
        "cron_expr": "0 17 * * 1-5",
        "description": "每日估值快照（PE/PB/股息率）",
    },
    "daily_kline_sync": {
        "cron_expr": "15 17 * * 1-5",
        "description": "日K线同步（关注+持仓股）",
    },
    "daily_prev_close_sync": {
        "cron_expr": "20 17 * * 1-5",
        "description": "prev_close同步（持仓+候选股，涨跌停校验用）",
    },
    "alert_evaluation": {
        "cron_expr": "30 17 * * 1-5",
        "description": "警报规则评估",
    },
    "daily_deep_sync": {
        "cron_expr": "0 18 * * 1-5",
        "description": "候选股深度数据同步（财报/K线/分红）",
    },
    "monthly_dividend_sync": {
        "cron_expr": "0 3 1 * *",
        "description": "月度分红记录同步",
    },
    "quarterly_financials_refresh": {
        "cron_expr": "0 4 25-31 3,4,8,10 *",
        "description": "季报财报数据刷新",
    },
    "quarterly_shareholders_refresh": {
        "cron_expr": "30 4 5 1,4,7,10 *",
        "description": "季度股东数据刷新",
    },
    "weekly_dividend_sync": {
        "cron_expr": "0 9 * * 1",
        "description": "周度分红历史同步（持仓+关注+候选股）",
    },
    "daily_corp_action_apply": {
        "cron_expr": "0 9 * * 1-5",
        "description": "每日公司行为应用（ex_date<=今日的 pending actions）",
    },
    "intraday_price_poll": {
        "cron_expr": "*/5 9-14 * * 1-5",
        "description": "盘中价格轮询（每5分钟，工作日 9-14 点；job 内还会做 trading_day + 时段校验）",
    },
    "pipeline_stale_sweep": {
        "cron_expr": "*/15 * * * *",  # every 15 min
        "description": "F15: 周期性清理 stuck pipeline runs (后台线程死亡但 status=running 的孤儿记录)",
    },
    "daily_draft_generation": {
        "cron_expr": "30 18 * * 1-5",  # weekdays 18:30, after daily syncs
        "description": "Phase5: BUY 报告价格入区间→生成 BUY 草稿 + 清过期草稿 (decision 9/10)",
    },
    # ── v2 LLM Pipeline jobs (2026-06-24) ─────────────────────────────
    "v2_quality_screen_weekly": {
        "cron_expr": "0 17 * * 6",  # every Saturday 17:00
        "description": "v2: quality_screen_pipeline 全市场扫描 → watchlist",
    },
    "v2_deep_research_weekly": {
        "cron_expr": "30 17 * * 6",  # every Saturday 17:30 (after quality_screen)
        "description": "v2: deep_research_pipeline 对 watchlist 前 10 家深度研究",
    },
    "v2_thesis_tracker_weekly": {
        "cron_expr": "0 18 * * 6",  # every Saturday 18:00
        "description": "v2: thesis_tracker_pipeline 对持仓每周复核论文",
    },
    # ── Sell trigger ───────────────────────────────────────────────────
    "daily_sell_trigger": {
        "cron_expr": "30 18 * * 1-5",  # weekdays 18:30, after draft generation
        "description": "Phase5: 卖出信号 2/3 (估值止盈+仓位超限) 每日扫描 → SELL 草稿",
    },
    "daily_index_sync": {
        "cron_expr": "0 19 * * 1-5",  # weekdays 19:00, after market close
        "description": "沪深300 日 K 线同步（组合评价基准对比用）",
    },
}


# Jobs disabled by default (opt-in via API)
_DISABLED_BY_DEFAULT: set[str] = {"intraday_price_poll"}


def _utcnow() -> datetime:
    return now()


def ensure_defaults(db: Session) -> int:
    """Insert default config for any job_id not yet in DB. Returns count of new rows."""
    inserted = 0
    for job_id, cfg in DEFAULT_JOBS.items():
        exists = db.query(SchedulerJob).filter(SchedulerJob.job_id == job_id).first()
        if not exists:
            db.add(
                SchedulerJob(
                    job_id=job_id,
                    cron_expr=cfg["cron_expr"],
                    description=cfg.get("description"),
                    enabled=job_id not in _DISABLED_BY_DEFAULT,
                )
            )
            inserted += 1
    if inserted:
        db.flush()
    return inserted


def get_all_configs(db: Session) -> list[SchedulerJob]:
    return db.query(SchedulerJob).order_by(SchedulerJob.job_id).all()


def get_config(db: Session, job_id: str) -> SchedulerJob | None:
    return db.query(SchedulerJob).filter(SchedulerJob.job_id == job_id).first()


def update_config(
    db: Session,
    job_id: str,
    *,
    cron_expr: str | None = None,
    enabled: bool | None = None,
) -> SchedulerJob | None:
    job = get_config(db, job_id)
    if not job:
        return None
    if cron_expr is not None:
        cron_to_trigger(cron_expr)  # validate
        job.cron_expr = cron_expr
    if enabled is not None:
        job.enabled = enabled
    db.flush()
    return job


# crontab standard: 0=Sun, 1=Mon, ..., 6=Sat, 7=Sun
# APScheduler CronTrigger.day_of_week: 0=Mon, 1=Tue, ..., 6=Sun
# `from_crontab()` passes the dow field verbatim — so crontab "1-5" (Mon-Fri)
# gets interpreted as APScheduler Tue-Sat, silently shifting all weekday jobs
# by one day. Translate the dow field before constructing the trigger.
_CRONTAB_DOW_TO_APS_NAME = {
    "0": "sun", "1": "mon", "2": "tue", "3": "wed", "4": "thu",
    "5": "fri", "6": "sat", "7": "sun",
}


def _translate_dow_field(dow: str) -> str:
    """Translate crontab dow field to APScheduler name-based equivalents.

    crontab allows: 0-7 (0/7=Sun, 1=Mon, ..., 6=Sat), `*`, ranges, lists, steps.
    APScheduler accepts named dows (mon/tue/.../sun) which are unambiguous.

    Examples:
      "1-5"     → "mon-fri"
      "0,6"     → "sun,sat"
      "*/5"     → "*/5"   (step not dow value, no translation needed)
      "*"       → "*"
      "1,3,5"   → "mon,wed,fri"
    """
    if dow == "*":
        return "*"
    parts = dow.split(",")
    translated_parts: list[str] = []
    for part in parts:
        if "/" in part:
            # step expression like */2 or 1-5/2 — keep as-is, step on full range
            translated_parts.append(part)
            continue
        if "-" in part:
            lo, hi = part.split("-", 1)
            lo_name = _CRONTAB_DOW_TO_APS_NAME.get(lo.strip())
            hi_name = _CRONTAB_DOW_TO_APS_NAME.get(hi.strip())
            if lo_name and hi_name:
                translated_parts.append(f"{lo_name}-{hi_name}")
            else:
                # Numeric range we don't recognize — fall back to raw
                translated_parts.append(part)
            continue
        name = _CRONTAB_DOW_TO_APS_NAME.get(part.strip())
        translated_parts.append(name if name else part)
    return ",".join(translated_parts)


def cron_to_trigger(cron_expr: str) -> CronTrigger:
    """Parse standard 5-field crontab into APScheduler CronTrigger.

    F14 (2026-06-18): APScheduler CronTrigger.day_of_week uses 0=Mon/6=Sun,
    while crontab standard uses 0=Sun/6=Sat. `from_crontab()` doesn't
    translate — so "1-5" (Mon-Fri) silently becomes Tue-Sat. We translate
    the dow field to APScheduler's named-dow form before constructing.
    """
    fields = cron_expr.split()
    if len(fields) != 5:
        raise ValueError(f"Invalid crontab expression (need 5 fields): {cron_expr!r}")
    minute, hour, day, month, dow = fields
    dow_translated = _translate_dow_field(dow)
    return CronTrigger(
        minute=minute, hour=hour, day=day, month=month,
        day_of_week=dow_translated,
        timezone="Asia/Shanghai",
    )


def record_start(db: Session, job_id: str) -> JobExecution:
    exec_ = JobExecution(
        job_id=job_id,
        status="running",
        started_at=_utcnow(),
    )
    db.add(exec_)
    db.flush()
    return exec_


def record_finish(
    db: Session,
    execution_id: int,
    status: str,
    result_summary: str | None = None,
    error_message: str | None = None,
) -> JobExecution | None:
    exec_ = db.query(JobExecution).filter(JobExecution.id == execution_id).first()
    if not exec_:
        return None
    now = _utcnow()
    exec_.finished_at = now
    exec_.status = status
    exec_.duration_ms = int((now - exec_.started_at).total_seconds() * 1000)
    exec_.result_summary = result_summary
    exec_.error_message = error_message
    db.flush()
    return exec_


def list_executions(
    db: Session,
    job_id: str | None = None,
    limit: int = 50,
) -> list[JobExecution]:
    q = db.query(JobExecution)
    if job_id:
        q = q.filter(JobExecution.job_id == job_id)
    return q.order_by(JobExecution.started_at.desc()).limit(limit).all()


def get_last_execution(db: Session, job_id: str) -> JobExecution | None:
    return (
        db.query(JobExecution)
        .filter(JobExecution.job_id == job_id)
        .order_by(JobExecution.started_at.desc())
        .first()
    )
