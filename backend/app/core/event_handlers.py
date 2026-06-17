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
    MonthlyBudgetExceeded,
    PlanEvaluationCompleted,
    ResearchRunCompleted,
    ResearchRunFailed,
    ThesisAlertTriggered,
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


# ── Serenity research handlers (Q17: route to NotificationChannel) ────────


def on_research_run_failed(event: ResearchRunFailed) -> None:
    """Serenity run failed → emit SystemAlert + dispatch to NotificationChannel."""
    from datetime import datetime, timezone

    from app.db.session import SessionLocal
    from app.models.system_alert import SystemAlert
    from app.services.notification_service import dispatch_alert

    alert = SystemAlert(
        severity="warning",
        category="research",
        message=f"Serenity 研究失败: {event.research_theme_name}",
        detail_json={
            "source": "research_runner",
            "title": f"Serenity 研究失败: {event.research_theme_name}",
            "theme_id": event.research_theme_id,
            "run_id": event.run_id,
            "attempts": event.attempt_count,
            "error": event.error[:500],
        },
    )
    with SessionLocal() as db:
        db.add(alert)
        db.commit()
        db.refresh(alert)
        dispatch_alert(db, alert)


def on_monthly_budget_exceeded(event: MonthlyBudgetExceeded) -> None:
    """Monthly LLM budget exceeded → emit SystemAlert (Q8 soft limit, alert only)."""
    from datetime import datetime, timezone

    from app.db.session import SessionLocal
    from app.models.system_alert import SystemAlert
    from app.services.notification_service import dispatch_alert

    alert = SystemAlert(
        severity="warning",
        category="research",
        message=f"Serenity 月度预算超限: {event.month}",
        detail_json={
            "source": "research_runner",
            "title": f"Serenity 月度预算超限: {event.month}",
            "month": event.month,
            "spend_cny": event.spend_cny,
            "budget_cny": event.budget_cny,
            "triggered_by_run_id": event.triggered_by_run_id,
            "hint": "软上限,仅告警不禁用。可在 .env 调整 SERENITY_MONTHLY_BUDGET_CNY。",
        },
    )
    with SessionLocal() as db:
        db.add(alert)
        db.commit()
        db.refresh(alert)
        dispatch_alert(db, alert)


# ── Phase 2 #9 阶段 B v2 handlers (2026-06-16) ────────────────────────────


def on_research_run_propose_claim_variables(event: ResearchRunCompleted) -> None:
    """serenity Run completed → propose claim variables via LLM (async).

    v2 Q5-C: half-automatic flow — LLM proposes, user reviews.
    v2 Q-new: failure / partial-failure are audit-logged so the Cockpit
    badge can surface them (red state).
    """
    from app.db.session import SessionLocal
    from app.services import audit_log_service
    from app.services.thesis_variable_proposal_service import propose_for_run
    from app.services.llm.zhipu_client import ZhipuClientError

    with SessionLocal() as db:
        try:
            result = propose_for_run(db, event.run_id)
        except ZhipuClientError as exc:
            logger.exception(
                "Claim variable proposal LLM call failed for run %s", event.run_id,
            )
            audit_log_service.write(
                db,
                entity_type="research_run",
                entity_id=str(event.run_id),
                event="claim_variable_proposal_failed",
                actor="system",
                summary=f"LLM error: {type(exc).__name__}: {str(exc)[:200]}",
                payload={"run_id": event.run_id, "error_type": type(exc).__name__},
            )
            db.commit()
            return
        except Exception:
            logger.exception(
                "Claim variable proposal crashed for run %s", event.run_id,
            )
            audit_log_service.write(
                db,
                entity_type="research_run",
                entity_id=str(event.run_id),
                event="claim_variable_proposal_failed",
                actor="system",
                summary="unexpected crash (see logs)",
                payload={"run_id": event.run_id},
            )
            db.commit()
            return

        if result.failed_count > 0:
            event_name = "claim_variable_proposal_partial"
        else:
            event_name = "claim_variable_proposed"
        audit_log_service.write(
            db,
            entity_type="research_run",
            entity_id=str(event.run_id),
            event=event_name,
            actor="system",
            summary=(
                f"proposed {result.proposed_count}/{result.total_claims}"
                f" (skipped: {result.skipped_count}, deduped: {result.deduped_count},"
                f" failed: {result.failed_count})"
            ),
            payload={
                "run_id": event.run_id,
                "proposed": result.proposed_count,
                "skipped": result.skipped_count,
                "deduped": result.deduped_count,
                "failed": result.failed_count,
                "failed_claim_ids": result.failed_claim_ids,
                "tokens_in": result.token_input,
                "tokens_out": result.token_output,
            },
        )
        db.commit()


def on_thesis_alert_triggered(event: ThesisAlertTriggered) -> None:
    """Thesis monitor breach → audit_log + notification dispatch + M4 sell draft.

    v2: dedup is enforced upstream via last_alerted_at. This handler
    always fires for fresh breaches only.

    M4 (Batch 5 2026-06-17): invest1 第13章 + invest2 §3 "渣男理论"
    论点证伪 → 自动生成 SELL draft (plan_id=NULL, step_kind='thesis_breach')
    + supersede 该 stock 的所有 pending BUY drafts.
    """
    from app.db.session import SessionLocal
    from app.services import audit_log_service
    from app.services.notification_service import dispatch_alert

    with SessionLocal() as db:
        audit_log_service.write(
            db,
            entity_type="research_claim_variable",
            entity_id=str(event.claim_var_id),
            event="thesis_alert_triggered",
            actor="system",
            stock_code=event.code,
            summary=event.message,
            payload={
                "claim_var_id": event.claim_var_id,
                "stock_code": event.code,
                "variable_name": event.variable_name,
                "current_value": event.current_value,
                "threshold": event.threshold_value,
                "breach_when": event.breach_when,
                "window_periods": event.window_periods,
            },
        )
        db.commit()

        # Best-effort notification dispatch. Failure here is logged only —
        # the audit_log above is the authoritative record.
        try:
            from app.models.system_alert import SystemAlert
            sa = SystemAlert(
                severity="alert",
                category="thesis",
                message=f"论点告警: {event.variable_name} ({event.code}) — {event.message}",
                detail_json={
                    "source": "thesis_monitor",
                    "claim_var_id": event.claim_var_id,
                    "stock_code": event.code,
                    "variable_name": event.variable_name,
                    "breach_when": event.breach_when,
                },
            )
            db.add(sa)
            db.commit()
            db.refresh(sa)
            dispatch_alert(db, sa)
        except Exception:
            logger.exception(
                "thesis alert notification dispatch failed cv_id=%s",
                event.claim_var_id,
            )

        # M4: auto-generate SELL draft + supersede pending BUYs (渣男理论)
        try:
            from app.services.draft_service import create_thesis_breach_sell_draft
            reason = (
                f"论点证伪: {event.variable_name} {event.breach_when} "
                f"{event.threshold_value} (current={event.current_value})"
            )
            draft = create_thesis_breach_sell_draft(
                db,
                stock_code=event.code,
                reason=reason,
                claim_var_id=event.claim_var_id,
                reduce_pct_of_position=1.0,  # 全部卖出
            )
            if draft:
                logger.info(
                    "M4 thesis_breach SELL draft created: id=%s code=%s cv_id=%s",
                    draft.id, event.code, event.claim_var_id,
                )
                db.commit()
            else:
                logger.info(
                    "M4 thesis_breach: no open holding for code=%s, no SELL draft created",
                    event.code,
                )
        except Exception:
            logger.exception(
                "M4 thesis_breach sell draft creation failed cv_id=%s code=%s",
                event.claim_var_id, event.code,
            )


# Register handlers with the event bus
bus.subscribe(DataSyncCompleted, on_valuation_sync_reassess_strategies)
bus.subscribe(DataSyncCompleted, on_financials_sync_thesis_variables)
bus.subscribe(DataSyncCompleted, on_kline_sync_price_alert)
bus.subscribe(DraftCreated, on_draft_check_position)
bus.subscribe(DraftCreated, on_draft_audit_log)
bus.subscribe(PlanEvaluationCompleted, on_plan_completed_check_alerts)
bus.subscribe(ResearchRunFailed, on_research_run_failed)
bus.subscribe(MonthlyBudgetExceeded, on_monthly_budget_exceeded)
bus.subscribe(ResearchRunCompleted, on_research_run_propose_claim_variables)
bus.subscribe(ThesisAlertTriggered, on_thesis_alert_triggered)
