"""Draft schemas (v2)."""

from datetime import datetime

from pydantic import BaseModel


class DraftExecute(BaseModel):
    """Confirm a draft's actual fill (P0-2).

    The user executes at the broker, then reports the *actual* price/quantity/
    time back. Recorded as a Trade (source=manual, source_ref=draft.id). May
    freely deviate from the draft's suggested values. When price+quantity are
    omitted the draft is just marked executed without a trade.
    """
    price: float | None = None
    quantity: int | None = None
    filled_at: datetime | None = None


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
