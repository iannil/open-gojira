"""SystemAlert API — list / resolve."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.system_alert import SystemAlert
from app.services.system_alert_service import (
    list_alerts, list_unresolved, resolve_alert, get_critical_unresolved_count,
)

router = APIRouter(prefix="/api/system-alerts", tags=["system-alerts"])


class SystemAlertResponse(BaseModel):
    id: int
    severity: str
    category: str
    message: str
    detail_json: dict | None
    created_at: datetime
    resolved_at: datetime | None
    resolved_by: str | None

    model_config = {"from_attributes": True}


class ResolvePayload(BaseModel):
    resolved_by: str = "manual"


@router.get("", response_model=list[SystemAlertResponse])
def api_list_alerts(
    severity: str | None = None,
    category: str | None = None,
    unresolved_only: bool = False,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    if unresolved_only:
        return list_unresolved(db, severity=severity, category=category, limit=limit)
    return list_alerts(db, severity=severity, category=category, limit=limit)


@router.get("/unresolved-count")
def api_critical_count(db: Session = Depends(get_db)):
    """For UI badge: count of critical unresolved alerts."""
    return {"count": get_critical_unresolved_count(db)}


@router.post("/{alert_id}/resolve", response_model=SystemAlertResponse)
def api_resolve(alert_id: int, payload: ResolvePayload, db: Session = Depends(get_db)):
    alert = resolve_alert(db, alert_id, resolved_by=payload.resolved_by)
    if not alert:
        raise HTTPException(404, "alert not found")
    db.commit()
    return alert
