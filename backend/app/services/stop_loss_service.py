"""Stop-loss / take-profit rule evaluation.

Triggers when price moves against (stop_loss) or in favor of (take_profit)
the position by configured threshold. Emits SystemAlert (critical for
stop loss, warning for take profit) and updates rule.triggered_at.

Does NOT auto-place SELL orders — generates strong recommendation draft
so user retains final decision authority.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Union

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.holding_risk_rule import HoldingRiskRule
from app.services.holding_view_service import get_holding_view
from app.services.system_alert_service import create_alert


logger = logging.getLogger(__name__)


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass(frozen=True)
class StopLossEvent:
    stock_code: str
    current_price: float
    cost_basis: float
    threshold_pct: float
    actual_pct: float
    rule_type: str  # pct_from_cost | trailing | fixed_price


@dataclass(frozen=True)
class TakeProfitEvent:
    stock_code: str
    current_price: float
    cost_basis: float
    threshold_pct: float
    actual_pct: float


def check_holding(
    db: Session, stock_code: str, current_price: float
) -> Optional[Union[StopLossEvent, TakeProfitEvent]]:
    """Evaluate stop-loss + take-profit rules for one holding.

    Returns StopLossEvent / TakeProfitEvent / None.
    Side effects: emits SystemAlert on trigger, updates rule.triggered_at
    + rule.peak_price (trailing mode).
    """
    # Find the rule (must be enabled + not yet triggered)
    rule = db.execute(
        select(HoldingRiskRule).where(
            HoldingRiskRule.stock_code == stock_code,
            HoldingRiskRule.enabled == True,  # noqa: E712
            HoldingRiskRule.triggered_at.is_(None),
        )
    ).scalar_one_or_none()
    if not rule:
        return None

    # Find current holding
    holdings = [h for h in get_holding_view(db) if h["stock_code"] == stock_code]
    if not holdings or holdings[0]["total_quantity"] <= 0:
        return None
    cost_basis = holdings[0]["avg_cost_basis"]

    # Trailing mode: tracks peak, triggers stop loss only
    if rule.stop_loss_type == "trailing":
        if rule.peak_price is None or current_price > rule.peak_price:
            rule.peak_price = current_price
            db.flush()
        # Stop triggers when current <= peak × (1 - stop_loss_pct)
        if rule.peak_price and rule.peak_price > 0:
            threshold = rule.peak_price * (1 - (rule.stop_loss_pct or 0))
            if current_price <= threshold:
                event = StopLossEvent(
                    stock_code=stock_code, current_price=current_price,
                    cost_basis=rule.peak_price,
                    threshold_pct=-(rule.stop_loss_pct or 0),
                    actual_pct=(current_price - rule.peak_price) / rule.peak_price,
                    rule_type="trailing",
                )
                _trigger(db, rule, event, "stop_loss")
                return event
        # Trailing only does stop loss (take profit handled by other rules)
        return None

    # pct_from_cost: standard mode — both stop loss + take profit
    if cost_basis > 0:
        pnl_pct = (current_price - cost_basis) / cost_basis

        # Stop loss check (price has fallen below threshold)
        if rule.stop_loss_pct is not None and pnl_pct <= -(rule.stop_loss_pct):
            event = StopLossEvent(
                stock_code=stock_code, current_price=current_price,
                cost_basis=cost_basis,
                threshold_pct=-(rule.stop_loss_pct),
                actual_pct=pnl_pct,
                rule_type="pct_from_cost",
            )
            _trigger(db, rule, event, "stop_loss")
            return event

        # Take profit check (price has risen above threshold)
        if rule.take_profit_pct is not None and pnl_pct >= rule.take_profit_pct:
            event = TakeProfitEvent(
                stock_code=stock_code, current_price=current_price,
                cost_basis=cost_basis,
                threshold_pct=rule.take_profit_pct,
                actual_pct=pnl_pct,
            )
            _trigger(db, rule, event, "take_profit")
            return event

    # fixed_price mode (deferred — not common for personal use)
    return None


def _trigger(
    db: Session,
    rule: HoldingRiskRule,
    event: Union[StopLossEvent, TakeProfitEvent],
    kind: str,
) -> None:
    """Mark rule triggered + emit SystemAlert."""
    rule.triggered_at = _utcnow_naive()
    rule.trigger_reason = (
        f"{kind}: price={event.current_price:.2f}, "
        f"actual_pct={event.actual_pct:+.2%}, threshold={event.threshold_pct:+.2%}"
    )
    db.flush()

    severity = "critical" if kind == "stop_loss" else "warning"
    create_alert(
        db,
        severity=severity,
        category="data",
        message=(
            f"{'止损' if kind == 'stop_loss' else '止盈'}触发 {event.stock_code}: "
            f"现价 ¥{event.current_price:.2f}, "
            f"{'成本' if kind == 'stop_loss' else '目标'} ¥{event.cost_basis:.2f}, "
            f"幅度 {event.actual_pct:+.2%}"
        ),
        detail={
            "stock_code": event.stock_code,
            "current_price": event.current_price,
            "cost_basis": event.cost_basis,
            "rule_type": getattr(event, "rule_type", "pct_from_cost"),
            "actual_pct": event.actual_pct,
            "threshold_pct": event.threshold_pct,
        },
    )
