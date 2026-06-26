"""Trade service — atomic write of trade + cash balance update.

Single entry point: record_trade(). This is the only place that inserts
into the trades table. All callers (manual entry UI, CSV import, broker
API, corp_action processor, migration script) go through here.

Invariants:
- trades + cash_balance written in same transaction (atomic)
- BUY: cash sufficient check before write
- SELL: T+1 available_quantity check before write (exchange rule)
- BUY/SELL: price within [prev_close × (1-limit), prev_close × (1+limit)]
  (A-share 涨跌停); bypassable via force=True (rare: 新股首日 / 复牌)
- DIVIDEND/CORP_ACTION: skip both price + T+1 checks (no tradeable
  price/quantity concept)
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.broker_fee_config import BrokerFeeConfig
from app.models.cash_balance import CashBalance
from app.models.stock import Stock
from app.models.trade import Trade
from app.services.fee_calculator_service import compute_fees
from app.services.price_validator_service import assert_tradable
from app.core.datetime_utils import now


def _available_quantity_at(db: Session, code: str, at_time=None) -> int:
    """T+1 sellable quantity derived from the Trade ledger (event sourcing,
    decision Q2-A 2026-06-26). Net held shares minus shares bought on the same
    calendar day (today's buys are frozen by the T+1 exchange rule)."""
    from app.services.position_service import available_quantity

    at_date = at_time.date() if at_time is not None else now().date()
    return available_quantity(db, code, at_date)


class InsufficientBalanceError(HTTPException):
    def __init__(self, required: float, available: float):
        super().__init__(
            status_code=400,
            detail=f"Insufficient cash: need ¥{required:.2f}, have ¥{available:.2f}",
        )


class InsufficientQuantityError(HTTPException):
    """SELL exceeds T+1 available quantity (today's buys are frozen)."""

    def __init__(self, code: str, requested: int, available: int, filled_at):
        super().__init__(
            status_code=400,
            detail=(
                f"Insufficient T+1 available quantity for {code}: "
                f"requested {requested}, available {available} at {filled_at}"
            ),
        )


class NoActiveFeeConfigError(HTTPException):
    def __init__(self, filled_at: date):
        super().__init__(
            status_code=500,
            detail=f"No active broker_fee_config with effective_from <= {filled_at}",
        )


def _utcnow() -> datetime:
    return now()


def _get_active_fee_config(db: Session, filled_at: datetime) -> BrokerFeeConfig:
    """Pick the most recent config active as of filled_at."""
    cfg = db.execute(
        select(BrokerFeeConfig)
        .where(
            BrokerFeeConfig.is_active == True,  # noqa: E712 — SQLAlchemy expression
            BrokerFeeConfig.effective_from <= filled_at.date(),
        )
        .order_by(BrokerFeeConfig.effective_from.desc())
        .limit(1)
    ).scalar_one_or_none()
    if not cfg:
        raise NoActiveFeeConfigError(filled_at.date())
    return cfg


def _ensure_cash_balance_row(db: Session) -> CashBalance:
    """Get singleton row, create with 0 balance if missing."""
    cb = db.query(CashBalance).first()
    if not cb:
        cb = CashBalance(id=1, balance=0.0)
        db.add(cb)
        db.flush()
    return cb


def record_trade(
    db: Session,
    *,
    stock_code: str,
    side: str,
    price: float,
    quantity: int,
    filled_at: datetime,
    source: str = "manual",
    source_ref: Optional[str] = None,
    fee_config: Optional[BrokerFeeConfig] = None,
    commission_override: Optional[float] = None,
    note: Optional[str] = None,
    force: bool = False,
) -> Trade:
    """Atomically write a trade and update cash_balance.

    Args:
        db: SQLAlchemy session.
        stock_code: e.g. "600519".
        side: "BUY" | "SELL" | "DIVIDEND" | "CORP_ACTION".
        price: Per-share price.
        quantity: Number of shares (always positive int; sign derived from side).
        filled_at: Execution time (Asia/Shanghai naive).
        source: "manual" | "csv_import" | "broker_api" | "corp_action" | "migration" | "reversal".
        source_ref: Optional reference (draft_id / corp_action_id / etc).
        fee_config: Force a specific config (e.g. for backtests). If None,
                    auto-select by filled_at.
        commission_override: Force commission value. If None, auto-compute.
        note: Optional human-readable note.
        force: Bypass price band check (BUY/SELL). Reserved for rare cases
               where 涨跌停 does not apply (新股首日 / 复牌 / 大宗交易).
               T+1 and cash checks are NEVER bypassed. When True, an audit
               marker is appended to ``note``.

    Returns:
        The created Trade.

    Raises:
        InsufficientBalanceError: BUY total_value > cash_balance.balance.
        InsufficientQuantityError: SELL quantity > available_quantity_at(filled_at).
        PriceOutOfBandError / StockSuspendedError / NoPrevCloseError: propagated
            from assert_tradable (only when force=False).
        NoActiveFeeConfigError: No broker_fee_config effective as of filled_at.
    """
    # Stock must exist (we need prev_close + listing_status for checks).
    stock = db.get(Stock, stock_code)
    if stock is None:
        raise HTTPException(404, f"Stock {stock_code} not found")

    # --- Hard constraints (only for BUY/SELL) ------------------------------
    # DIVIDEND / CORP_ACTION have no tradeable price/quantity concept; skip.
    if side in ("BUY", "SELL"):
        # 1. Price band check — bypassable via force (audit trail in note).
        if not force:
            assert_tradable(stock, price, filled_at.date())

        # 2. T+1 check (SELL only) — NEVER bypassed (exchange would reject).
        if side == "SELL":
            available = _available_quantity_at(db, stock_code, filled_at)
            if quantity > available:
                raise InsufficientQuantityError(
                    stock_code, quantity, available, filled_at,
                )

    cfg = fee_config or _get_active_fee_config(db, filled_at)
    fees = compute_fees(side=side, price=price, quantity=quantity, broker_config=cfg)
    commission = (
        commission_override if commission_override is not None
        else fees.commission
    )
    fee_source = "manual_override" if commission_override is not None else "auto"

    # Compute total_value with the effective commission.
    # total_value's sign and direction differ by side (see FeeBreakdown.total_value).
    if side == "BUY":
        # cash outflow = notional + commission + stamp_duty + transfer_fee
        total_value = fees.notional + commission + fees.stamp_duty + fees.transfer_fee
    elif side == "SELL":
        # cash inflow = notional - commission - stamp_duty - transfer_fee
        total_value = fees.notional - commission - fees.stamp_duty - fees.transfer_fee
    elif side == "DIVIDEND":
        # negative total_value indicates cash inflow; commission/fees are 0 already
        total_value = -fees.notional
    elif side == "CORP_ACTION":
        # no cash impact
        total_value = 0.0
    else:
        raise ValueError(f"Unknown side: {side}")

    # Signed quantity:
    # BUY: +N | SELL: -N | DIVIDEND: 0 | CORP_ACTION: +N (preserved; corp_action
    # may add or remove shares but caller is responsible for sign-of-event type)
    if side == "BUY":
        signed_qty = quantity
    elif side == "SELL":
        signed_qty = -quantity
    elif side == "DIVIDEND":
        signed_qty = 0
    elif side == "CORP_ACTION":
        signed_qty = quantity
    else:
        raise ValueError(f"Unknown side: {side}")

    cb = _ensure_cash_balance_row(db)

    # Cash sufficiency check for BUY only
    if side == "BUY":
        if cb.balance < total_value:
            raise InsufficientBalanceError(required=total_value, available=cb.balance)

    # force=True → audit trail marker appended to note
    final_note = note
    if force:
        marker = "[FORCE: price band bypassed]"
        final_note = f"{marker} {note}" if note else marker

    # Write trade
    trade = Trade(
        stock_code=stock_code,
        side=side,
        price=price,
        quantity=signed_qty,
        filled_at=filled_at,
        commission=commission,
        stamp_duty=fees.stamp_duty,
        transfer_fee=fees.transfer_fee,
        total_value=total_value,
        source=source,
        source_ref=source_ref,
        fee_source=fee_source,
        note=final_note,
    )
    db.add(trade)
    db.flush()  # populate trade.id

    # Update cash_balance (same transaction — atomic)
    if side == "BUY":
        cb.balance -= total_value
    elif side == "SELL":
        cb.balance += total_value
    elif side == "DIVIDEND":
        # total_value is negative for DIVIDEND → adding -total_value yields positive inflow
        cb.balance += -total_value
    # CORP_ACTION: no cash impact (no balance change)
    cb.last_trade_id = trade.id
    cb.as_of_at = _utcnow()
    db.flush()
    return trade
