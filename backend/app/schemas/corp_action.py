"""Pydantic schemas for CorpAction API (S4A.4)."""
from datetime import date, datetime

from pydantic import BaseModel, Field


class CorpActionResponse(BaseModel):
    """Public representation of a CorpAction row."""

    id: int
    stock_code: str
    ex_date: date
    action_type: str
    params_json: dict
    source: str
    created_at: datetime
    processed_at: datetime | None = None
    applied_trade_id: int | None = None
    note: str | None = None

    model_config = {"from_attributes": True}


class ProcessPendingResponse(BaseModel):
    """Result of POST /api/corp-actions/process-pending."""

    processed_count: int
    skipped_count: int = 0


class ProcessOneResponse(BaseModel):
    """Result of POST /api/corp-actions/{id}/process — same shape as the row."""

    id: int
    stock_code: str
    ex_date: date
    action_type: str
    params_json: dict
    source: str
    created_at: datetime
    processed_at: datetime | None = None
    applied_trade_id: int | None = None
    note: str | None = None

    model_config = {"from_attributes": True}


class SyncDividendsRequest(BaseModel):
    """Request body for manual dividend sync trigger."""

    stock_codes: list[str] = Field(..., min_length=1)
    start_date: str | None = None
    end_date: str | None = None


class SyncDividendsResponse(BaseModel):
    """Result of POST /api/corp-actions/sync-dividends."""

    new_count: int
    failed_codes: list[str] = Field(default_factory=list)
