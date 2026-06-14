"""Scheduler configuration and execution tracking service."""

import logging
from datetime import datetime, timezone

from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

from app.models.scheduler_config import JobExecution, SchedulerJob

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
    "daily_cycle_assessment": {
        "cron_expr": "5 17 * * 1-5",
        "description": "市场周期评估（沪深300 PE/PB 百分位）",
    },
    "daily_kline_sync": {
        "cron_expr": "15 17 * * 1-5",
        "description": "日K线同步（关注+持仓股）",
    },
    "daily_prev_close_sync": {
        "cron_expr": "20 17 * * 1-5",
        "description": "prev_close同步（持仓+关注+候选股，涨跌停校验用）",
    },
    "alert_evaluation": {
        "cron_expr": "30 17 * * 1-5",
        "description": "警报规则评估",
    },
    "daily_plan_evaluation": {
        "cron_expr": "45 17 * * 1-5",
        "description": "预案自动评估（筛选+评分）",
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
    "weekly_rebalancing_review": {
        "cron_expr": "0 10 * * 0",
        "description": "周度再平衡检查",
    },
    "monthly_thesis_variable_sync": {
        "cron_expr": "30 4 1 * *",
        "description": "月度论点变量同步",
    },
    "weekly_business_pattern_inference": {
        "cron_expr": "30 4 * * 0",
        "description": "周度 BusinessPattern 推断（跳过用户已 override 的股票）",
    },
    "intraday_monitor": {
        "cron_expr": "*/5 9-14 * * 1-5",
        "description": "盘中价格监控（每5分钟检查止盈告警，默认关闭）",
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
}


# Jobs disabled by default (opt-in via API)
_DISABLED_BY_DEFAULT: set[str] = {"intraday_monitor", "intraday_price_poll"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


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


def cron_to_trigger(cron_expr: str) -> CronTrigger:
    """Parse standard 5-field crontab into APScheduler CronTrigger."""
    return CronTrigger.from_crontab(cron_expr, timezone="Asia/Shanghai")


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
