"""Event handler registrations — imported once at startup to wire the event bus.

Each handler subscribes to a specific event type. Handlers run synchronously
during emit(); exceptions are caught by EventBus and logged.

v2 (2026-06-26): removed v1 handlers (strategy reassessment, thesis variable
sync, position advisor, plan alerts, v1 serenity research handlers). Kept:
  - on_kline_sync_price_alert (no-op for stale event compatibility)
  - on_draft_audit_log (v2: records DraftCreated → audit_log)
  - on_monthly_budget_exceeded (v2: LLM cost tracking alert)
  - on_thesis_alert_triggered (v2: M4 thesis breach → SELL draft）

Handler errors propagate to EventBus which logs them with structured context.
Inner try/except only wraps per-item loops to allow partial completion.
"""

from __future__ import annotations

import logging

from app.core.events import (
    DataSyncCompleted,
    DraftCreated,
    MonthlyBudgetExceeded,
    ThesisAlertTriggered,
    bus,
)

logger = logging.getLogger(__name__)

MAX_STOCKS_PER_HANDLER = 50


# ── Data sync handlers ─────────────────────────────────────────────────────


def on_kline_sync_price_alert(event: DataSyncCompleted) -> None:
    """K线同步完成 → 价格相关告警 (retired 2026-06-26).

    唯一用途是 stop_profit 止盈告警,已随 decision 2-A 退役 (止盈改由 sell_trigger
    处理,持仓改 Trade 派生无 stop_profit_price)。保留空壳以兼容事件注册。
    """
    return


# ── Business flow handlers ─────────────────────────────────────────────────


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


def on_monthly_budget_exceeded(event: MonthlyBudgetExceeded) -> None:
    """Monthly LLM budget exceeded → emit SystemAlert (Q8 soft limit, alert only)."""
    from datetime import datetime, timezone

    from app.db.session import SessionLocal
    from app.models.system_alert import SystemAlert
    from app.services.notification_service import dispatch_alert

    alert = SystemAlert(
        severity="warning",
        category="research",
        message=f"LLM 月度预算超限: {event.month}",
        detail_json={
            "source": "cost_tracker",
            "title": f"LLM 月度预算超限: {event.month}",
            "month": event.month,
            "spend_cny": event.spend_cny,
            "budget_cny": event.budget_cny,
            "triggered_by_run_id": event.triggered_by_run_id,
            "hint": "软上限,仅告警不禁用。可在 .env 调整。",
        },
    )
    with SessionLocal() as db:
        db.add(alert)
        db.commit()
        db.refresh(alert)
        dispatch_alert(db, alert)


def on_thesis_alert_triggered(event: ThesisAlertTriggered) -> None:
    """Thesis monitor breach → audit_log + notification dispatch + M4 sell draft.

    M4 (Batch 5): invest1 第13章 + invest2 §3 "渣男理论"
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

        # Best-effort notification dispatch.
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
                reduce_pct_of_position=1.0,
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
bus.subscribe(DataSyncCompleted, on_kline_sync_price_alert)
bus.subscribe(DraftCreated, on_draft_audit_log)
bus.subscribe(MonthlyBudgetExceeded, on_monthly_budget_exceeded)
bus.subscribe(ThesisAlertTriggered, on_thesis_alert_triggered)
