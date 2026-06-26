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
    """Draft API response (v2 + Phase 5 draft_generator fields)."""
    id: int
    plan_id: int | None = None
    code: str
    side: str
    status: str
    step_kind: str
    step_index: int
    add_pct: float | None = None
    reduce_pct_of_position: float | None = None
    suggested_quantity: int | None = None
    reason: str
    source: str = "evaluator"
    # Phase 5 draft_generator fields
    research_report_id: int | None = None
    target_price: float | None = None
    strategy_tier: str | None = None
    sizing_logic: str | None = None
    thesis_status: str | None = None
    expires_at: datetime | None = None
    serenity_thesis: str | None = None
    triggered_at: datetime | None = None
    executed_at: datetime | None = None
