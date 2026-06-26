"""Order-draft endpoints (autopilot's "应买/应卖" list).

v2 (2026-06-24): simplified. v1 backfill-suggestion endpoint removed (draft_matcher_service deleted).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.draft import DraftExecute, DraftResponse
from app.services import audit_log_service, draft_service
from app.services.decision_audit_service import record_decision
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
        suggested_quantity=draft.suggested_quantity,
        reason=draft.reason,
        source=getattr(draft, "source", "evaluator") or "evaluator",
        research_report_id=draft.research_report_id,
        target_price=draft.target_price,
        strategy_tier=draft.strategy_tier,
        sizing_logic=draft.sizing_logic,
        thesis_status=draft.thesis_status,
        expires_at=draft.expires_at,
        serenity_thesis=draft.serenity_thesis,
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
    audit_payload: dict = {}

    if payload.price and payload.quantity:
        from app.services.trade_service import record_trade
        side = "BUY" if draft.side == "BUY" else "SELL"
        trade = record_trade(
            db,
            stock_code=draft.code,
            side=side,
            price=float(payload.price),
            quantity=int(payload.quantity),
            filled_at=payload.filled_at or now(),
            source="manual",
            source_ref=str(draft.id),
            note=f"Confirmed fill of draft #{draft.id}: {draft.reason}",
        )
        audit_payload["trade_id"] = trade.id
        # Q2-A: the position derives from this Trade — no Holding row to create.

        # Phase 6 Tier 2: record decision audit for P&L tracking
        record_decision(db, draft=draft, trade=trade)

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
