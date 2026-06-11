"""Schemas for the audit-log timeline."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class AuditLogResponse(BaseModel):
    id: int
    entity_type: str
    entity_id: Optional[str] = None
    event: str
    actor: str
    stock_code: Optional[str] = None
    summary: str
    payload: Optional[dict[str, Any]] = None
    created_at: Optional[datetime] = None
