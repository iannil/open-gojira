"""Event handler registrations — imported once at startup to wire the event bus.

Each handler subscribes to a specific event type. Handlers run synchronously
during emit(); exceptions are caught by EventBus and logged.

Handler errors propagate to EventBus which logs them with structured context.
Inner try/except only wraps per-item loops to allow partial completion.
"""

from __future__ import annotations

import logging

from app.core.events import (
    DataSyncCompleted,
    DraftCreated,
    PlanEvaluationCompleted,
    bus,
)

logger = logging.getLogger(__name__)

MAX_STOCKS_PER_HANDLER = 50


# ── Data sync handlers ─────────────────────────────────────────────────────


def on_valuation_sync_reassess_strategies(event: DataSyncCompleted) -> None:
    """估值同步完成 → 重评估 watchlist 中相关股票的策略。"""
    if event.pipeline_type != "valuations" or event.status == "failed":
        return
    if not event.stock_codes:
        return

    from app.db.session import SessionLocal
    with SessionLocal() as db:
        from app.services import watchlist_service
        watched = set(watchlist_service.all_watched_codes(db))
        codes_to_eval = [c for c in event.stock_codes if c in watched]
        if not codes_to_eval:
            return

        if len(codes_to_eval) > MAX_STOCKS_PER_HANDLER:
            logger.warning(
                "on_valuation_sync_reassess_strategies: truncating %d → %d codes",
                len(codes_to_eval), MAX_STOCKS_PER_HANDLER,
            )
            codes_to_eval = codes_to_eval[:MAX_STOCKS_PER_HANDLER]

        from app.services.stock_context_builder import build_context
        from app.services.strategy_engine import evaluate as strategy_evaluate
        from app.schemas.strategy import StrategyRule
        from app.models.strategy import Strategy

        strategies = db.query(Strategy).all()
        for code in codes_to_eval:
            try:
                ctx = build_context(db, code)
                for s in strategies:
                    rule = StrategyRule.model_validate_json(s.rule_json)
                    strategy_evaluate(rule, ctx)
            except Exception:
                logger.exception("strategy reassess failed for %s", code)
        db.commit()


def on_financials_sync_thesis_variables(event: DataSyncCompleted) -> None:
    """财报同步完成 → 自动同步论点变量。"""
    if event.pipeline_type != "financials" or event.status == "failed":
        return
    if not event.stock_codes:
        return

    from app.db.session import SessionLocal
    with SessionLocal() as db:
        from app.services.thesis_variable_sync_service import sync_stock
        codes = event.stock_codes[:MAX_STOCKS_PER_HANDLER]
        for code in codes:
            try:
                sync_stock(db, code, audit=True)
            except Exception:
                logger.exception("thesis variable sync failed for %s", code)
        db.commit()


def on_kline_sync_price_alert(event: DataSyncCompleted) -> None:
    """K线同步完成 → 检查价格相关告警规则。"""
    if event.pipeline_type != "klines" or event.status == "failed":
        return
    if not event.stock_codes:
        return

    from app.db.session import SessionLocal
    with SessionLocal() as db:
        from app.services.alert_service import list_rules
        stop_profit_rules = [
            r for r in list_rules(db, enabled_only=True)
            if r.rule_type == "stop_profit" and r.stock_code in event.stock_codes
        ]
        if not stop_profit_rules:
            return

        from app.services.alert_service import _fetch_realtime, _eval_stop_profit, _should_dedupe
        realtime = _fetch_realtime([r.stock_code for r in stop_profit_rules if r.stock_code])
        for rule in stop_profit_rules:
            if _should_dedupe(db, rule):
                continue
            try:
                snapshot = realtime.get(rule.stock_code) if rule.stock_code else None
                _eval_stop_profit(db, rule, snapshot)
            except Exception:
                logger.exception("stop_profit eval failed for rule %d", rule.id)
        db.commit()


# ── Business flow handlers ─────────────────────────────────────────────────


def on_draft_check_position(event: DraftCreated) -> None:
    """Draft 创建后 → 检查仓位约束并记录结果。"""
    if event.direction != "BUY":
        return

    from app.db.session import SessionLocal
    with SessionLocal() as db:
        from app.services.position_advisor_service import check_before_draft
        advice = check_before_draft(db, event.stock_code, event.direction)
        if advice.blockers:
            logger.warning(
                "DraftCreated position check: draft_id=%d code=%s blockers=%s",
                event.draft_id, event.stock_code, advice.blockers,
            )


def on_draft_audit_log(event: DraftCreated) -> None:
    """Draft 创建后 → 记录审计日志。"""
    from app.db.session import SessionLocal
    with SessionLocal() as db:
        from app.services.audit_log_service import write
        write(
            db,
            entity_type="draft",
            entity_id=str(event.draft_id),
            event="draft_created",
            summary=f"{event.direction} {event.stock_code}",
            stock_code=event.stock_code,
            actor="plan_evaluator",
            payload={
                "direction": event.direction,
                "plan_id": event.plan_id,
                "add_pct": event.add_pct,
                "reduce_pct_of_position": event.reduce_pct_of_position,
            },
        )
        db.commit()


def on_plan_completed_check_alerts(event: PlanEvaluationCompleted) -> None:
    """Plan 评估完成 → 检查新候选是否触发告警规则。"""
    if event.passed == 0:
        return

    from app.db.session import SessionLocal
    with SessionLocal() as db:
        from app.models.candidate import Candidate
        from sqlalchemy import select
        new_candidates = db.execute(
            select(Candidate.stock_code).where(
                Candidate.plan_id == event.plan_id,
                Candidate.status == "active",
            )
        ).scalars().all()
        if not new_candidates:
            return

        from app.services.alert_service import list_rules
        rules = list_rules(db, enabled_only=True)
        stock_rules = [r for r in rules if r.stock_code in new_candidates]
        if not stock_rules:
            return

        from app.services.alert_service import (
            _fetch_realtime, _eval_dividend_ex_date_near,
            _eval_financial_report_released, _eval_stop_profit,
            _should_dedupe,
        )
        realtime = _fetch_realtime([r.stock_code for r in stock_rules if r.stock_code])
        for rule in stock_rules:
            if _should_dedupe(db, rule):
                continue
            try:
                snapshot = realtime.get(rule.stock_code) if rule.stock_code else None
                if rule.rule_type == "dividend_ex_date_near":
                    _eval_dividend_ex_date_near(db, rule)
                elif rule.rule_type == "financial_report_released":
                    _eval_financial_report_released(db, rule)
                elif rule.rule_type == "stop_profit":
                    _eval_stop_profit(db, rule, snapshot)
            except Exception:
                logger.exception("alert eval failed for rule %d", rule.id)
        db.commit()


# For testing
_sync_handlers = [on_valuation_sync_reassess_strategies, on_financials_sync_thesis_variables, on_kline_sync_price_alert]

# Register handlers with the event bus
bus.subscribe(DataSyncCompleted, on_valuation_sync_reassess_strategies)
bus.subscribe(DataSyncCompleted, on_financials_sync_thesis_variables)
bus.subscribe(DataSyncCompleted, on_kline_sync_price_alert)
bus.subscribe(DraftCreated, on_draft_check_position)
bus.subscribe(DraftCreated, on_draft_audit_log)
bus.subscribe(PlanEvaluationCompleted, on_plan_completed_check_alerts)
