"""Read-only audit-log timeline (autopilot black box)."""

import json
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.audit_log import AuditLogResponse
from app.services import audit_log_service

router = APIRouter(prefix="/api/audit-log", tags=["audit_log"])


def _decode_payload(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _to_response(row) -> AuditLogResponse:
    return AuditLogResponse(
        id=row.id,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        event=row.event,
        actor=row.actor,
        stock_code=row.stock_code,
        summary=row.summary,
        payload=_decode_payload(row.payload),
        created_at=row.created_at,
    )


@router.get("", response_model=list[AuditLogResponse])
def list_logs(
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    event: str | None = Query(default=None),
    stock_code: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[AuditLogResponse]:
    rows = audit_log_service.recent(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        event=event,
        stock_code=stock_code,
        limit=limit,
    )
    return [_to_response(r) for r in rows]
