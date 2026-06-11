"""Alert endpoints — rule CRUD + event listing + manual evaluation."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.alert import (
    AlertEvaluateResponse,
    AlertEventResponse,
    AlertRuleCreate,
    AlertRuleResponse,
    AlertRuleUpdate,
)
from app.schemas.common import AckedResponse, CountResponse, OkResponse
from app.services import alert_service as svc

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


# ── Rules ─────────────────────────────────────────────────────────────────


@router.get("/rules", response_model=list[AlertRuleResponse])
def api_list_rules(enabled_only: bool = False, db: Session = Depends(get_db)):
    return [_rule_to_response(r) for r in svc.list_rules(db, enabled_only=enabled_only)]


@router.post("/rules", response_model=AlertRuleResponse, status_code=201)
def api_create_rule(payload: AlertRuleCreate, db: Session = Depends(get_db)):
    rule = svc.create_rule(db, payload.model_dump())
    return _rule_to_response(rule)


@router.put("/rules/{rule_id}", response_model=AlertRuleResponse)
def api_update_rule(rule_id: int, payload: AlertRuleUpdate, db: Session = Depends(get_db)):
    rule = svc.update_rule(db, rule_id, payload.model_dump(exclude_unset=True))
    return _rule_to_response(rule)


@router.delete("/rules/{rule_id}", response_model=OkResponse)
def api_delete_rule(rule_id: int, db: Session = Depends(get_db)):
    if not svc.delete_rule(db, rule_id):
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")
    return {"ok": True}


# ── Events ────────────────────────────────────────────────────────────────


@router.get("/events", response_model=list[AlertEventResponse])
def api_list_events(
    acked: Optional[bool] = None,
    stock_code: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    return [_event_to_response(e) for e in svc.list_events(db, acked=acked, stock_code=stock_code, limit=limit)]


@router.get("/events/unacked-count", response_model=CountResponse)
def api_unacked_count(db: Session = Depends(get_db)):
    return {"count": svc.unacked_count(db)}


@router.post("/events/{event_id}/ack", response_model=AlertEventResponse)
def api_ack(event_id: int, db: Session = Depends(get_db)):
    return _event_to_response(svc.ack_event(db, event_id))


@router.post("/events/ack-all", response_model=AckedResponse)
def api_ack_all(db: Session = Depends(get_db)):
    return {"acked": svc.ack_all_events(db)}


# ── Engine ────────────────────────────────────────────────────────────────


@router.post("/evaluate", response_model=AlertEvaluateResponse)
def api_evaluate(db: Session = Depends(get_db)):
    return svc.evaluate_all_rules(db)


@router.post("/rules/sync-from-watchlist")
def api_sync_from_watchlist(db: Session = Depends(get_db)):
    """Reconcile auto-rules generated from watchlist item thresholds."""
    return svc.sync_rules_from_watchlist(db)


# ── Helpers ───────────────────────────────────────────────────────────────


def _rule_to_response(rule) -> AlertRuleResponse:
    return AlertRuleResponse(
        id=rule.id,
        rule_type=rule.rule_type,
        stock_code=rule.stock_code,
        params=rule.params or {},
        enabled=rule.enabled,
        note=rule.note,
        created_at=str(rule.created_at) if rule.created_at else None,
        last_evaluated_at=str(rule.last_evaluated_at) if rule.last_evaluated_at else None,
    )


def _event_to_response(ev) -> AlertEventResponse:
    return AlertEventResponse(
        id=ev.id,
        rule_id=ev.rule_id,
        stock_code=ev.stock_code,
        rule_type=ev.rule_type,
        title=ev.title,
        detail=ev.detail,
        payload=ev.payload or {},
        severity=ev.severity,
        fired_at=str(ev.fired_at) if ev.fired_at else None,
        acked=ev.acked,
        acked_at=str(ev.acked_at) if ev.acked_at else None,
    )
