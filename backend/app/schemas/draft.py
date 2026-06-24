"""Draft schemas (v2)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class DraftExecute(BaseModel):
    """Payload for executing a draft."""
    buy_price: float | None = None
    quantity: int | None = None
    holding_id: int | None = None
    auto_create_holding: bool = True
    discipline_checklist: dict[str, Any] | None = None


class DraftResponse(BaseModel):
    """Draft API response."""
    id: int
    plan_id: int | None = None
    code: str
    side: str
    status: str
    step_kind: str
    step_index: int
    add_pct: float | None = None
    reduce_pct_of_position: float | None = None
    reason: str
    source: str = "evaluator"
    triggered_at: datetime | None = None
    executed_at: datetime | None = None
