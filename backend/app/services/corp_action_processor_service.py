"""Apply pending CorpActions to holdings + cash_balance.

Each action_type has its own applier:
- cash_dividend: emit DIVIDEND trade (cash inflow per share × qty held)
- stock_dividend: emit CORP_ACTION trade (add quantity, price=0)
- capitalization: emit CORP_ACTION trade (add quantity, price=0)
- delist: mark Stock.listing_status (no trade)
- merger: emit SELL on old code + BUY on new code (at ratio)
- rights_issue: do NOT auto-apply; emit warning system_alert

All actions update CorpAction.processed_at + applied_trade_id.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Callable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cash_balance import CashBalance
from app.models.corp_action import CorpAction
from app.models.stock import Stock
from app.models.trade import Trade
from app.services.system_alert_service import create_alert
from app.core.datetime_utils import now


logger = logging.getLogger(__name__)


def _utcnow_naive() -> datetime:
    return now()


def _ensure_cash_balance_row(db: Session) -> CashBalance:
    """Get singleton row, create with 0 balance if missing."""
    cb = db.query(CashBalance).first()
    if not cb:
        cb = CashBalance(id=1, balance=0.0)
        db.add(cb)
        db.flush()
    return cb


# --- per-type appliers ---

def _apply_cash_dividend(db: Session, action: CorpAction, qty_held: int) -> Optional[Trade]:
    """Create DIVIDEND trade for cash inflow.

    cash_inflow = per_share × qty_held; stored as negative total_value
    (negative = cash inflow per Trade.total_value convention).
    """
    if qty_held <= 0:
        return None
    per_share = float(action.params_json.get("per_share", 0))
    if per_share <= 0:
        return None
    cash_inflow = per_share * qty_held
    trade = Trade(
        stock_code=action.stock_code,
        side="DIVIDEND",
        price=0.0,
        quantity=0,
        filled_at=_utcnow_naive(),
        commission=0.0, stamp_duty=0.0, transfer_fee=0.0,
        total_value=-cash_inflow,  # negative = inflow
        source="corp_action",
        source_ref=str(action.id),
        fee_source="auto",
        note=f"Cash dividend ¥{per_share:.4f}/share × {qty_held} = ¥{cash_inflow:.2f}",
    )
    db.add(trade)
    db.flush()
    cb = _ensure_cash_balance_row(db)
    cb.balance += cash_inflow
    cb.last_trade_id = trade.id
    cb.as_of_at = _utcnow_naive()
    return trade


def _apply_quantity_change(
    db: Session, action: CorpAction, qty_held: int, action_label: str
) -> Optional[Trade]:
    """Handle stock_dividend + capitalization: add quantity, price=0.

    new_shares = int(qty_held × per_10_shares / 10).
    No cash impact.
    """
    if qty_held <= 0:
        return None
    per_10 = float(action.params_json.get("per_10_shares", 0))
    if per_10 <= 0:
        return None
    new_shares = int(qty_held * per_10 / 10)
    if new_shares <= 0:
        return None
    trade = Trade(
        stock_code=action.stock_code,
        side="CORP_ACTION",
        price=0.0,
        quantity=new_shares,
        filled_at=_utcnow_naive(),
        commission=0.0, stamp_duty=0.0, transfer_fee=0.0,
        total_value=0.0,
        source="corp_action",
        source_ref=str(action.id),
        fee_source="auto",
        note=f"{action_label}: {per_10} per 10 shares × {qty_held} = +{new_shares}",
    )
    db.add(trade)
    db.flush()
    # No cash impact for CORP_ACTION; still refresh last_trade_id / as_of_at
    cb = db.query(CashBalance).first()
    if cb:
        cb.last_trade_id = trade.id
        cb.as_of_at = _utcnow_naive()
    return trade


def _apply_stock_dividend(db: Session, action: CorpAction, qty_held: int) -> Optional[Trade]:
    return _apply_quantity_change(db, action, qty_held, "Stock dividend")


def _apply_capitalization(db: Session, action: CorpAction, qty_held: int) -> Optional[Trade]:
    return _apply_quantity_change(db, action, qty_held, "Capitalization")


def _apply_delist(db: Session, action: CorpAction, qty_held: int) -> Optional[Trade]:
    """Mark Stock.listing_status as delisting_transitional_period.

    No trade created. The holding itself is left as-is for the user to
    manually dispose / write off in the Review screen.
    """
    stock = db.get(Stock, action.stock_code)
    if stock and stock.listing_status != "delisting_transitional_period":
        stock.listing_status = "delisting_transitional_period"
    return None


def _apply_merger(db: Session, action: CorpAction, qty_held: int) -> Optional[Trade]:
    """Convert old code shares to new code at ratio.

    Generates two trades atomically:
    - SELL on old code (quantity = -qty_held, total_value=0 — valuation changes
      handled separately; price=0 keeps cash neutral)
    - BUY on new code (quantity = int(qty_held × ratio))

    Returns the BUY trade (so applied_trade_id points to the incoming
    position, which is what the user cares about post-merger).
    """
    if qty_held <= 0:
        return None
    new_code = action.params_json.get("new_code")
    ratio = float(action.params_json.get("ratio", 1.0))
    if not new_code or ratio <= 0:
        return None
    new_shares = int(qty_held * ratio)

    sell_trade = Trade(
        stock_code=action.stock_code, side="SELL",
        price=0.0, quantity=-qty_held,
        filled_at=_utcnow_naive(),
        commission=0.0, stamp_duty=0.0, transfer_fee=0.0,
        total_value=0.0,
        source="corp_action", source_ref=str(action.id),
        fee_source="auto",
        note=f"Merger: {qty_held} shares converted to {new_code} at ratio {ratio}",
    )
    db.add(sell_trade)
    db.flush()
    buy_trade = Trade(
        stock_code=new_code, side="BUY",
        price=0.0, quantity=new_shares,
        filled_at=_utcnow_naive(),
        commission=0.0, stamp_duty=0.0, transfer_fee=0.0,
        total_value=0.0,
        source="corp_action", source_ref=str(action.id),
        fee_source="auto",
        note=f"Merger: received {new_shares} shares from {action.stock_code} (ratio {ratio})",
    )
    db.add(buy_trade)
    db.flush()
    return buy_trade  # link to buy trade


def _apply_rights_issue(db: Session, action: CorpAction, qty_held: int) -> Optional[Trade]:
    """Don't auto-apply. Emit warning system_alert.

    Rights issues require explicit user decision (subscribe / waive /
    sell rights). Lixinger has no reliable source for these per S0.1 spike.
    We mark the action as processed so we don't re-alert on every batch run;
    if the user wants to revisit, they can resolve the alert and re-add.
    """
    if qty_held <= 0:
        return None
    create_alert(
        db,
        severity="warning",
        category="data",
        message=(
            f"配股 action pending for {action.stock_code}: "
            f"{action.params_json.get('per_10_shares', '?')} per 10 shares @ "
            f"¥{action.params_json.get('subscription_price', '?')} "
            f"(end: {action.params_json.get('subscription_end', '?')}). "
            f"User decision required."
        ),
        detail={
            "corp_action_id": action.id,
            "stock_code": action.stock_code,
            "qty_held": qty_held,
            **action.params_json,
        },
    )
    return None


# --- dispatcher ---

_APPLIERS: dict[str, Callable] = {
    "cash_dividend": _apply_cash_dividend,
    "stock_dividend": _apply_stock_dividend,
    "capitalization": _apply_capitalization,
    "delist": _apply_delist,
    "merger": _apply_merger,
    "rights_issue": _apply_rights_issue,
    # code_change handled like merger (new_code + ratio=1.0)
    "code_change": _apply_merger,
}


def process_one(db: Session, action: CorpAction) -> CorpAction:
    """Apply a single CorpAction. Idempotent: skip if already processed."""
    if action.processed_at is not None:
        return action

    # Find current qty held for this stock (trade-derived open position, Q2-A)
    from app.services import position_service

    pos = position_service.position_for(db, action.stock_code, price_lookup=lambda _c: None)
    qty_held = pos.quantity if pos else 0

    applier = _APPLIERS.get(action.action_type)
    if not applier:
        logger.warning("Unknown action_type %s, skipping", action.action_type)
        action.processed_at = _utcnow_naive()
        action.note = f"Unknown action_type {action.action_type}, skipped"
        db.flush()
        return action

    try:
        trade = applier(db, action, qty_held)
        action.processed_at = _utcnow_naive()
        if trade:
            action.applied_trade_id = trade.id
        db.flush()
    except Exception as e:
        logger.error("Failed to apply corp_action %s: %s", action.id, e)
        # Don't mark as processed — leave for retry
        raise

    return action


def process_pending_corp_actions(
    db: Session,
    *,
    as_of: Optional[date] = None,
) -> int:
    """Process all pending CorpActions (optionally filtered by ex_date <= as_of).

    Returns count of actions processed.
    """
    stmt = (
        select(CorpAction)
        .where(CorpAction.processed_at.is_(None))
        .order_by(CorpAction.ex_date.asc())
    )
    if as_of:
        stmt = stmt.where(CorpAction.ex_date <= as_of)

    pending = list(db.execute(stmt).scalars().all())
    count = 0
    for action in pending:
        try:
            process_one(db, action)
            count += 1
        except Exception as e:
            logger.error("Aborting batch at corp_action %s: %s", action.id, e)
            break
    db.flush()
    return count
