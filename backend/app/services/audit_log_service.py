"""Structured audit log — the autopilot's black box.

`write(...)` flushes (no commit) so it composes inside the caller's transaction.
Standalone callers (scheduler jobs) commit themselves.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


def write(
    db: Session,
    *,
    entity_type: str,
    event: str,
    summary: str,
    entity_id: Optional[str] = None,
    actor: str = "system",
    stock_code: Optional[str] = None,
    payload: Optional[dict[str, Any]] = None,
) -> AuditLog:
    row = AuditLog(
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        event=event,
        actor=actor,
        stock_code=stock_code,
        summary=summary[:500],
        payload=json.dumps(payload, ensure_ascii=False, default=str) if payload else None,
    )
    db.add(row)
    try:
        db.flush()
    except Exception:  # noqa: BLE001
        logger.exception(
            "audit_log flush failed entity=%s event=%s", entity_type, event
        )
    return row


def recent(
    db: Session,
    *,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    event: Optional[str] = None,
    stock_code: Optional[str] = None,
    limit: int = 100,
) -> list[AuditLog]:
    q = db.query(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    if entity_type:
        q = q.filter(AuditLog.entity_type == entity_type)
    if entity_id:
        q = q.filter(AuditLog.entity_id == entity_id)
    if event:
        q = q.filter(AuditLog.event == event)
    if stock_code:
        q = q.filter(AuditLog.stock_code == stock_code)
    return q.limit(limit).all()
