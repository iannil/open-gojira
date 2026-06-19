"""Order-draft endpoints (autopilot's "应买/应卖" list)."""

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.plan import DraftExecute, DraftResponse
from app.schemas.review import BackfillSuggestionResponse
from app.services import audit_log_service, draft_service
from app.core.datetime_utils import now

router = APIRouter(prefix="/api/drafts", tags=["drafts"])


def _to_response(draft) -> DraftResponse:
    return DraftResponse(
        id=draft.id,
        plan_id=draft.plan_id,
        code=draft.code,
        side=draft.side,
        status=draft.status,
        step_kind=draft.step_kind,
        step_index=draft.step_index,
        add_pct=draft.add_pct,
        reduce_pct_of_position=draft.reduce_pct_of_position,
        reason=draft.reason,
        source=getattr(draft, "source", "evaluator") or "evaluator",
        triggered_at=draft.triggered_at,
        executed_at=draft.executed_at,
    )


@router.get("", response_model=list[DraftResponse])
def list_drafts(
    status: str | None = None,
    code: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    rows = draft_service.list_recent(db, status=status, code=code, limit=limit)
    return [_to_response(r) for r in rows]


@router.post("/{draft_id}/execute", response_model=DraftResponse)
def execute_draft(
    draft_id: int,
    payload: DraftExecute | None = None,
    force: bool = False,
    db: Session = Depends(get_db),
):
    payload = payload or DraftExecute()
    draft = draft_service.execute(db, draft_id)
    audit_payload = {"holding_id": payload.holding_id}

    # 重审 #2 (2026-06-13): merge execute + trade entry into one step.
    # When broker fill (buy_price + quantity) is provided, record a Trade
    # atomically — user no longer needs to re-enter the same fill on
    # TradesPage. source_ref ties the trade back to this draft.
    if payload.buy_price and payload.quantity:
        from app.services.trade_service import record_trade
        from datetime import datetime
        side = "BUY" if draft.side == "BUY" else "SELL"
        trade = record_trade(
            db,
            stock_code=draft.code,
            side=side,
            price=float(payload.buy_price),
            quantity=int(payload.quantity),
            filled_at=now(),
            source="draft",
            source_ref=str(draft.id),
            note=f"Auto from draft #{draft.id}: {draft.reason}",
        )
        audit_payload["auto_trade_id"] = trade.id

        # F29 (2026-06-18): materialize a Holding for BUY so Cockpit
        # portfolio_summary (which reads holdings table) reflects the new
        # position. Industry-cap (F20) is enforced via create_holding's
        # force param; pass through user-supplied force to allow conscious
        # override (matches /api/portfolio pattern). On breach without force,
        # raise 409 and let the whole transaction roll back (atomic with the
        # trade above).
        if payload.auto_create_holding and side == "BUY":
            from app.services.holding_service import create_holding
            from datetime import date as _date
            holding = create_holding(db, {
                "stock_code": draft.code,
                "buy_date": _date.today(),
                "buy_price": float(payload.buy_price),
                "quantity": int(payload.quantity),
                "stop_profit_price": 0.0,  # 0 = disabled; user can edit later
                "trade_rationale": draft.reason,
            }, force=force)
            audit_payload["auto_holding_id"] = holding.id

    if payload.discipline_checklist:
        audit_payload["discipline_checklist"] = payload.discipline_checklist
    audit_log_service.write(
        db,
        entity_type="draft",
        entity_id=str(draft.id),
        event="executed",
        actor="user",
        stock_code=draft.code,
        summary=f"{draft.side} {draft.code} executed (step={draft.step_kind}[{draft.step_index}])",
        payload=audit_payload,
    )
    db.commit()
    return _to_response(draft)


@router.post("/{draft_id}/cancel", response_model=DraftResponse)
def cancel_draft(draft_id: int, db: Session = Depends(get_db)):
    draft = draft_service.cancel(db, draft_id)
    audit_log_service.write(
        db,
        entity_type="draft",
        entity_id=str(draft.id),
        event="cancelled",
        actor="user",
        stock_code=draft.code,
        summary=f"{draft.side} {draft.code} draft cancelled",
    )
    db.commit()
    return _to_response(draft)


@router.get("/{draft_id}/backfill-suggestion", response_model=BackfillSuggestionResponse)
def get_backfill_suggestion(draft_id: int, db: Session = Depends(get_db)):
    """Get a smart backfill suggestion for a draft."""
    from app.services.draft_matcher_service import suggest
    result = suggest(db, draft_id)
    if result is None:
        return {"action": "none", "message": "Draft not found"}
    return result.to_dict()
