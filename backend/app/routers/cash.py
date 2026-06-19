"""Cash API — singleton balance + adjustment log."""
from app.core.datetime_utils import now

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.cash_adjustment import CashAdjustment
from app.models.cash_balance import CashBalance
from app.schemas.cash import (
    CashAdjustmentCreate,
    CashAdjustmentResponse,
    CashBalanceResponse,
)

router = APIRouter(prefix="/api/cash", tags=["cash"])


def _utcnow() -> datetime:
    return now()


def _ensure_balance_row(db: Session) -> CashBalance:
    cb = db.execute(select(CashBalance)).scalar_one_or_none()
    if not cb:
        cb = CashBalance(id=1, balance=0.0)
        db.add(cb)
        db.flush()
    return cb


@router.get("/balance", response_model=CashBalanceResponse)
def get_balance(db: Session = Depends(get_db)):
    """Return singleton balance row, creating it with 0 if missing."""
    return _ensure_balance_row(db)


@router.get("/adjustments", response_model=list[CashAdjustmentResponse])
def list_adjustments(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List cash adjustments, newest first."""
    stmt = (
        select(CashAdjustment)
        .order_by(desc(CashAdjustment.happened_at), desc(CashAdjustment.id))
        .offset(offset)
        .limit(limit)
    )
    return list(db.execute(stmt).scalars().all())


@router.post("/adjustments", response_model=CashAdjustmentResponse, status_code=201)
def create_adjustment(payload: CashAdjustmentCreate, db: Session = Depends(get_db)):
    """Record a deposit/withdrawal and update cash_balance atomically."""
    adj = CashAdjustment(
        amount=payload.amount,
        happened_at=payload.happened_at,
        reason=payload.reason,
        note=payload.note,
    )
    db.add(adj)
    db.flush()

    cb = _ensure_balance_row(db)
    cb.balance += payload.amount
    cb.last_adjustment_id = adj.id
    cb.as_of_at = _utcnow()

    db.commit()
    db.refresh(adj)
    return adj
