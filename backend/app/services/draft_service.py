"""Draft service — persistence + execute / cancel transitions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.draft import Draft
from app.models.plan import Plan
from app.core.events import bus, DraftCreated


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


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
    plan: Plan,
    stock_code: str,
    side: str,
    step_kind: str,
    step_index: int,
    reason: str,
    add_pct: Optional[float] = None,
    reduce_pct_of_position: Optional[float] = None,
) -> Optional[Draft]:
    """Persist a Draft for a candidate stock evaluated by the plan.

    Idempotent: if a pending draft with the same plan/stock/step already exists,
    update it in place instead of creating a duplicate.

    Cooldown: if a non-pending draft for the same plan/stock/step exists within
    the cooldown period, skip emission and return None.
    """
    # Cooldown check: skip if a recent non-pending draft exists within cooldown period
    if plan.trading_rules_json:
        try:
            from app.schemas.plan import TradingRules
            rules = TradingRules.model_validate_json(plan.trading_rules_json)
            if rules.cooldown_days > 0:
                cutoff = _utcnow() - timedelta(days=rules.cooldown_days)
                recent = db.execute(
                    select(Draft).where(
                        Draft.plan_id == plan.id,
                        Draft.code == stock_code,
                        Draft.step_kind == step_kind,
                        Draft.step_index == step_index,
                        Draft.status.in_(["executed", "cancelled"]),
                        Draft.triggered_at >= cutoff,
                    )
                ).scalar_one_or_none()
                if recent:
                    return None  # Within cooldown, skip
        except Exception:
            pass  # Best-effort cooldown check

    existing = db.execute(
        select(Draft).where(
            Draft.plan_id == plan.id,
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
        existing.triggered_at = _utcnow()
        db.flush()
        try:
            bus.emit_async(DraftCreated(
                draft_id=existing.id,
                stock_code=stock_code,
                direction=side,
                plan_id=plan.id,
                add_pct=add_pct,
                reduce_pct_of_position=reduce_pct_of_position,
            ))
        except Exception:
            import logging as _logging
            _logging.getLogger(__name__).exception("EventBus emit_async DraftCreated failed for draft")
        return existing

    draft = Draft(
        plan_id=plan.id,
        code=stock_code,
        side=side,
        step_kind=step_kind,
        step_index=step_index,
        add_pct=add_pct,
        reduce_pct_of_position=reduce_pct_of_position,
        reason=reason,
    )
    db.add(draft)
    db.flush()
    try:
        bus.emit_async(DraftCreated(
            draft_id=draft.id,
            stock_code=stock_code,
            direction=side,
            plan_id=plan.id,
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
