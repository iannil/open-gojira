"""Trades API — CRUD + manual entry + reversal.

All trades flow through trade_service.record_trade() so cash_balance is
updated atomically. Reversal creates an opposite-side trade and refunds/
deducts cash inside the same transaction.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.cash_balance import CashBalance
from app.models.trade import Trade
from app.schemas.trade import TradeCreate, TradeListResponse, TradeResponse
from app.services.trade_service import record_trade

router = APIRouter(prefix="/api/trades", tags=["trades"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


_OPPOSITE_SIDE = {
    "BUY": "SELL",
    "SELL": "BUY",
    "DIVIDEND": "DIVIDEND",  # reversal of a dividend inflow is an outflow
    "CORP_ACTION": "CORP_ACTION",
}


@router.post("", response_model=TradeResponse, status_code=201)
def create_trade(payload: TradeCreate, db: Session = Depends(get_db)):
    """Record a new trade (manual entry, csv import, or broker api)."""
    trade = record_trade(
        db,
        stock_code=payload.stock_code,
        side=payload.side,
        price=payload.price,
        quantity=payload.quantity,
        filled_at=payload.filled_at,
        source=payload.source,
        source_ref=payload.source_ref,
        commission_override=payload.commission_override,
        note=payload.note,
    )
    db.commit()
    db.refresh(trade)
    return trade


@router.get("", response_model=TradeListResponse)
def list_trades(
    code: str | None = None,
    side: str | None = None,
    source: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List trades with optional filters, newest first."""
    filters = []
    if code:
        filters.append(Trade.stock_code == code)
    if side:
        filters.append(Trade.side == side)
    if source:
        filters.append(Trade.source == source)

    base = select(Trade)
    if filters:
        base = base.where(*filters)

    items = list(
        db.execute(
            base.order_by(desc(Trade.filled_at), desc(Trade.id)).offset(offset).limit(limit)
        ).scalars().all()
    )

    count_stmt = select(func.count()).select_from(Trade)
    if filters:
        count_stmt = count_stmt.where(*filters)
    total = int(db.execute(count_stmt).scalar() or 0)

    return TradeListResponse(items=items, total=total)


@router.get("/{trade_id}", response_model=TradeResponse)
def get_trade(trade_id: int, db: Session = Depends(get_db)):
    trade = db.get(Trade, trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")
    return trade


@router.post("/{trade_id}/reverse", response_model=TradeResponse, status_code=201)
def reverse_trade(trade_id: int, db: Session = Depends(get_db)):
    """Reverse a trade by creating an opposite-side trade linked back.

    - Original trade's ``reversed_by_trade_id`` is set to the new trade's id.
    - cash_balance is adjusted by negating the original total_value direction.
    - Reversal trades cannot themselves be reversed.
    """
    original = db.get(Trade, trade_id)
    if not original:
        raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")
    if original.reversed_by_trade_id is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Trade {trade_id} already reversed by #{original.reversed_by_trade_id}",
        )
    if original.source == "reversal":
        raise HTTPException(status_code=400, detail="Cannot reverse a reversal trade")

    opposite_side = _OPPOSITE_SIDE.get(original.side)
    if opposite_side is None:
        raise HTTPException(status_code=400, detail=f"Cannot reverse side={original.side}")

    # Build the reversal trade directly (bypass record_trade's BUY cash check —
    # a reversal is always allowed because it merely undoes a prior effect).
    reversal = Trade(
        stock_code=original.stock_code,
        side=opposite_side,
        price=original.price,
        quantity=-original.quantity,
        filled_at=_utcnow(),
        commission=-original.commission,
        stamp_duty=-original.stamp_duty,
        transfer_fee=-original.transfer_fee,
        total_value=-original.total_value,
        source="reversal",
        source_ref=str(original.id),
        fee_source="auto",
        note=f"Reversal of Trade#{original.id}",
    )
    db.add(reversal)
    db.flush()  # populate reversal.id

    original.reversed_by_trade_id = reversal.id

    # Mirror the cash impact. We negate the original total_value's signed
    # contribution to cash_balance using the same convention as record_trade.
    cb = db.execute(select(CashBalance)).scalar_one_or_none()
    if not cb:
        cb = CashBalance(id=1, balance=0.0)
        db.add(cb)
        db.flush()

    if original.side == "BUY":
        # original deducted total_value from cash; reversal refunds it
        cb.balance += original.total_value
    elif original.side == "SELL":
        # original added total_value to cash; reversal deducts it
        cb.balance -= original.total_value
    elif original.side == "DIVIDEND":
        # original added -total_value (inflow); reversal deducts the same
        cb.balance -= -original.total_value
    # CORP_ACTION: no cash impact on either side

    cb.last_trade_id = reversal.id
    cb.as_of_at = _utcnow()

    db.commit()
    db.refresh(reversal)
    return reversal
