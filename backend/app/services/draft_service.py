"""Draft service — persistence + execute / cancel transitions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.draft import Draft
from app.core.events import bus, DraftCreated
from app.core.datetime_utils import now


def _utcnow() -> datetime:
    return now()


def list_recent(
    db: Session,
    *,
    status: Optional[str] = None,
    code: Optional[str] = None,
    limit: int = 100,
) -> list[Draft]:
    stmt = select(Draft).order_by(desc(Draft.triggered_at))
    if status:
        stmt = stmt.where(Draft.status == status)
    if code:
        stmt = stmt.where(Draft.code == code)
    return list(db.execute(stmt.limit(limit)).scalars().all())


def list_pending(db: Session) -> list[Draft]:
    return list_recent(db, status="pending", limit=500)


def emit(
    db: Session,
    *,
    plan: Optional[Any] = None,
    stock_code: str,
    side: str,
    step_kind: str,
    step_index: int,
    reason: str,
    add_pct: Optional[float] = None,
    reduce_pct_of_position: Optional[float] = None,
    suggested_quantity: Optional[int] = None,
) -> Optional[Draft]:
    """v2 stub: emit() is preserved for backward compatibility but no longer
    takes a Plan. v2 draft generation will be added in Phase 5 via
    draft_generator.py.
    """
    plan_id = getattr(plan, "id", None) if plan else None

    existing = db.execute(
        select(Draft).where(
            Draft.code == stock_code,
            Draft.step_kind == step_kind,
            Draft.step_index == step_index,
            Draft.status == "pending",
        )
    ).scalar_one_or_none()

    if existing:
        existing.reason = reason
        existing.add_pct = add_pct
        existing.reduce_pct_of_position = reduce_pct_of_position
        existing.suggested_quantity = suggested_quantity
        existing.triggered_at = _utcnow()
        db.flush()
        try:
            bus.emit_async(DraftCreated(
                draft_id=existing.id,
                stock_code=stock_code,
                direction=side,
                plan_id=plan_id,
                add_pct=add_pct,
                reduce_pct_of_position=reduce_pct_of_position,
            ))
        except Exception:
            import logging as _logging
            _logging.getLogger(__name__).exception("EventBus emit_async DraftCreated failed for draft")
        return existing

    draft = Draft(
        plan_id=plan_id,
        code=stock_code,
        side=side,
        step_kind=step_kind,
        step_index=step_index,
        add_pct=add_pct,
        reduce_pct_of_position=reduce_pct_of_position,
        suggested_quantity=suggested_quantity,
        reason=reason,
    )
    db.add(draft)
    db.flush()
    try:
        bus.emit_async(DraftCreated(
            draft_id=draft.id,
            stock_code=stock_code,
            direction=side,
            plan_id=plan_id,
            add_pct=add_pct,
            reduce_pct_of_position=reduce_pct_of_position,
        ))
    except Exception:
        import logging as _logging
        _logging.getLogger(__name__).exception("EventBus emit_async DraftCreated failed for draft")
    return draft


def execute(
    db: Session,
    draft_id: int,
) -> Draft:
    draft = db.get(Draft, draft_id)
    if draft is None:
        raise HTTPException(404, "draft not found")
    if draft.status != "pending":
        raise HTTPException(409, f"draft already {draft.status}")
    draft.status = "executed"
    draft.executed_at = _utcnow()
    db.flush()
    return draft


def cancel(db: Session, draft_id: int) -> Draft:
    draft = db.get(Draft, draft_id)
    if draft is None:
        raise HTTPException(404, "draft not found")
    if draft.status != "pending":
        raise HTTPException(409, f"draft already {draft.status}")
    draft.status = "cancelled"
    db.flush()
    return draft


def create_thesis_breach_sell_draft(
    db: Session,
    *,
    stock_code: str,
    reason: str,
    claim_var_id: int | None = None,
    reduce_pct_of_position: float = 1.0,
) -> Optional[Draft]:
    """M4 (Batch 5 2026-06-17): auto-generate SELL draft on thesis breach.

    invest1 第13章 + invest2 §3 "渣男理论: 不谈恋爱,只谈逻辑".
    论点证伪 → 自动生成 sell draft (pending, 用户 execute) + supersede 该 stock
    的所有 pending BUY drafts (避免告警后还自动加仓).

    Args:
        stock_code: breached stock code
        reason: human-readable breach detail (e.g. "OCF/NI 持续 2 期 < 0.5")
        claim_var_id: optional FK to research_claim_variables
        reduce_pct_of_position: 1.0 = 全部卖出 (默认), 0.5 = 减半

    Returns:
        Draft if created; None if no open holding exists for this stock.
    """
    from app.services.holding_view_service import get_holding_view

    # Gate: only create if stock is actually held
    holdings = get_holding_view(db)
    if not any(h["stock_code"] == stock_code for h in holdings):
        return None

    # Supersede all pending BUY drafts for this stock (避免告警后还自动加仓)
    superseded_count = _supersede_pending_buys_for_stock(db, stock_code)

    # Create the SELL draft. plan_id is nullable for system-generated drafts.
    existing_sell = db.execute(
        select(Draft).where(
            Draft.code == stock_code,
            Draft.side == "SELL",
            Draft.status == "pending",
            Draft.step_kind == "thesis_breach",
        )
    ).scalar_one_or_none()

    reason_full = f"[M4 渣男理论] {reason}"
    if claim_var_id is not None:
        reason_full += f" (claim_var_id={claim_var_id})"
    if superseded_count > 0:
        reason_full += f" | superseded {superseded_count} pending BUY drafts"

    if existing_sell:
        existing_sell.reason = reason_full
        existing_sell.reduce_pct_of_position = reduce_pct_of_position
        existing_sell.triggered_at = _utcnow()
        db.flush()
        return existing_sell

    draft = Draft(
        plan_id=None,
        code=stock_code,
        side="SELL",
        step_kind="thesis_breach",
        step_index=0,
        add_pct=None,
        reduce_pct_of_position=reduce_pct_of_position,
        suggested_quantity=None,
        reason=reason_full,
    )
    db.add(draft)
    db.flush()

    try:
        bus.emit_async(DraftCreated(
            draft_id=draft.id,
            stock_code=stock_code,
            direction="SELL",
            plan_id=None,
            add_pct=None,
            reduce_pct_of_position=reduce_pct_of_position,
        ))
    except Exception:
        import logging as _logging
        _logging.getLogger(__name__).exception(
            "EventBus emit_async DraftCreated failed for thesis_breach sell draft"
        )
    return draft


def _supersede_pending_buys_for_stock(db: Session, stock_code: str) -> int:
    """M4 helper: mark all pending BUY drafts for a stock as 'superseded'.

    Returns count of superseded drafts. Used when thesis breach fires so the
    system does not continue to suggest adding to a position whose thesis broke.
    """
    pending_buys = db.execute(
        select(Draft).where(
            Draft.code == stock_code,
            Draft.side == "BUY",
            Draft.status == "pending",
        )
    ).scalars().all()
    count = 0
    for d in pending_buys:
        d.status = "superseded"
        count += 1
    if count:
        db.flush()
    return count
