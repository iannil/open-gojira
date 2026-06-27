"""Native @task implementations for trading-related jobs."""

import logging

from app.db.session import SessionLocal
from app.services.task import TaskContext, task

logger = logging.getLogger(__name__)


@task(
    name="daily_draft_generation",
    cron="30 18 * * 1-5",
    retry=2,
    timeout=600,
    tags=["draft", "buy"],
    description="BUY 报告价格入区间→生成 BUY 草稿 + 清过期草稿",
)
def daily_draft_generation(ctx: TaskContext) -> dict:
    """Generate BUY drafts from fresh reports whose price entered a buy tier."""
    from app.services import draft_generator

    ctx.report_progress(0.0, "Generating BUY drafts")

    with SessionLocal() as db:
        try:
            result = draft_generator.generate_buy_drafts(db)
            db.commit()
            ctx.report_progress(1.0, "Draft generation complete")
            return result
        except Exception:
            db.rollback()
            logger.exception("daily_draft_generation failed")
            ctx.report_progress(1.0, "Failed")
            return {"error": "see logs"}


@task(
    name="daily_sell_trigger",
    cron="30 18 * * 1-5",
    retry=2,
    timeout=600,
    tags=["draft", "sell"],
    description="卖出信号 2/3 (估值止盈+仓位超限) 每日扫描 → SELL 草稿",
)
def daily_sell_trigger(ctx: TaskContext) -> dict:
    """Run sell signals 2 (valuation > 1.3x) and 3 (position > 15%)."""
    from app.services import sell_trigger

    ctx.report_progress(0.0, "Evaluating sell signals")

    with SessionLocal() as db:
        try:
            result = sell_trigger.run_all_signals(db)
            db.commit()
            ctx.report_progress(1.0, "Sell evaluation complete")
            return result
        except Exception:
            db.rollback()
            logger.exception("daily_sell_trigger failed")
            ctx.report_progress(1.0, "Failed")
            return {"error": "see logs"}


@task(
    name="intraday_price_poll",
    cron="*/5 9-14 * * 1-5",
    retry=1,
    timeout=120,
    tags=["market"],
    description="盘中价格轮询（每5分钟；默认禁用）",
)
def intraday_price_poll(ctx: TaskContext) -> dict:
    """Poll realtime prices every 5 min during A-share trading hours."""
    from datetime import date, datetime as _dt
    from app.models.system_alert import SystemAlert
    from app.services.intraday_monitor_service import poll_once
    from app.services.notification_service import dispatch_alert
    from app.services.trading_calendar_service import is_trading_day
    from sqlalchemy import select

    ctx.report_progress(0.0, "Checking trading day/time")

    with SessionLocal() as db:
        if not is_trading_day(db, date.today()):
            ctx.report_progress(1.0, "Non-trading day")
            return {"skipped": "non_trading_day"}

        now = _dt.now()
        hour_min = now.hour * 100 + now.minute
        in_morning = 930 <= hour_min <= 1130
        in_afternoon = 1300 <= hour_min <= 1500
        if not (in_morning or in_afternoon):
            ctx.report_progress(1.0, "Outside trading hours")
            return {"skipped": "outside_trading_hours"}

        ctx.report_progress(0.3, "Polling prices")
        result = poll_once(db)

        from datetime import timedelta
        from app.core.datetime_utils import now as _utcnow

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
                logger.warning("Dispatch failed for alert %s: %s", alert.id, e)
        db.commit()

        summary = {
            "codes_checked": result.codes_checked,
            "prices_fetched": result.prices_fetched,
            "stop_loss_events": len(result.stop_loss_events),
            "take_profit_events": len(result.take_profit_events),
            "errors": len(result.errors),
            "dispatched_alerts": dispatched,
        }
        ctx.report_progress(1.0, f"Poll complete: {summary}")
        return summary
