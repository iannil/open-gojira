"""CorpActions API (S4A.4).

Exposes the S4A.1-S4A.3 corp_action pipeline as REST endpoints:

- list/filter (status / action_type / source / stock_code)
- pending (sorted by ex_date asc for "what to apply next")
- single process / batch process (delegates to processor_service)
- manual dividend sync trigger (delegates to sync_service)

The scheduler (see app.scheduler.daily_corp_action_apply /
weekly_dividend_sync) calls the same services; this router is the manual /
UI surface.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.corp_action import CorpAction
from app.schemas.corp_action import (
    CorpActionResponse,
    ProcessOneResponse,
    ProcessPendingResponse,
    SyncDividendsRequest,
    SyncDividendsResponse,
)
from app.services.corp_action_processor_service import (
    process_one,
    process_pending_corp_actions,
)
from app.services.corp_action_sync_service import sync_dividends_batch

router = APIRouter(prefix="/api/corp-actions", tags=["corp-actions"])


@router.get("", response_model=list[CorpActionResponse])
def list_actions(
    stock_code: str | None = None,
    action_type: str | None = None,
    source: str | None = None,
    status: str | None = Query(
        None,
        description='"pending" | "processed". Omit for all.',
    ),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[CorpAction]:
    """List corp_actions with optional filters.

    Default sort is ex_date desc (most recent first) for human scanability.
    Use ``status=pending`` for the actionable queue.
    """
    stmt = select(CorpAction).order_by(desc(CorpAction.ex_date))
    if stock_code:
        stmt = stmt.where(CorpAction.stock_code == stock_code)
    if action_type:
        stmt = stmt.where(CorpAction.action_type == action_type)
    if source:
        stmt = stmt.where(CorpAction.source == source)
    if status == "pending":
        stmt = stmt.where(CorpAction.processed_at.is_(None))
    elif status == "processed":
        stmt = stmt.where(CorpAction.processed_at.is_not(None))
    elif status is not None:
        raise HTTPException(
            400,
            "status must be 'pending' or 'processed'",
        )
    return list(db.execute(stmt.limit(limit)).scalars().all())


@router.get("/pending", response_model=list[CorpActionResponse])
def list_pending(
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[CorpAction]:
    """Convenience endpoint: pending actions sorted by ex_date asc.

    This is the order the daily scheduler applies them in, so it's also the
    right view for the Cockpit "what will be applied next" card.
    """
    stmt = (
        select(CorpAction)
        .where(CorpAction.processed_at.is_(None))
        .order_by(CorpAction.ex_date.asc())
        .limit(limit)
    )
    return list(db.execute(stmt).scalars().all())


@router.get("/{action_id}", response_model=CorpActionResponse)
def get_action(action_id: int, db: Session = Depends(get_db)) -> CorpAction:
    a = db.get(CorpAction, action_id)
    if not a:
        raise HTTPException(404, f"corp_action {action_id} not found")
    return a


@router.post("/{action_id}/process", response_model=ProcessOneResponse)
def api_process_one(
    action_id: int, db: Session = Depends(get_db),
) -> CorpAction:
    """Apply a single corp_action. Idempotent (no-op if already processed)."""
    a = db.get(CorpAction, action_id)
    if not a:
        raise HTTPException(404, f"corp_action {action_id} not found")
    try:
        process_one(db, a)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Process failed: {e}") from e
    db.refresh(a)
    return a


@router.post("/process-pending", response_model=ProcessPendingResponse)
def api_process_pending(db: Session = Depends(get_db)) -> ProcessPendingResponse:
    """Batch-apply all pending corp_actions (ex_date asc)."""
    try:
        count = process_pending_corp_actions(db)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Batch process failed: {e}") from e
    return ProcessPendingResponse(processed_count=count)


@router.post("/sync-dividends", response_model=SyncDividendsResponse)
def api_sync_dividends(
    payload: SyncDividendsRequest, db: Session = Depends(get_db),
) -> SyncDividendsResponse:
    """Trigger a manual dividend sync for the given stock codes.

    Useful for backfilling after adding new holdings/watchlist items.
    """
    try:
        # sync_dividends_batch commits internally per stock.
        count = sync_dividends_batch(db, payload.stock_codes)
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Sync failed: {e}") from e
    return SyncDividendsResponse(new_count=count)
