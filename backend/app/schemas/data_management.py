"""Schemas for data management endpoints."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ── Stock search & pool ──────────────────────────────────────────────────

class StockSearchResult(BaseModel):
    code: str
    name: str
    industry: Optional[str] = None
    listed_date: Optional[str] = None


class StockPoolAddRequest(BaseModel):
    stock_codes: list[str] = Field(..., min_length=1)


class StockPoolRemoveRequest(BaseModel):
    stock_codes: list[str] = Field(..., min_length=1)


class DataCompleteness(BaseModel):
    has_valuation: bool = False
    has_financial: bool = False
    has_kline: bool = False
    has_dividend: bool = False


class StockPoolItem(BaseModel):
    code: str
    name: str
    industry: Optional[str] = None
    tier: Optional[str] = None
    security_theme: Optional[str] = None
    added_at: Optional[str] = None
    data_completeness: DataCompleteness


# ── Data status overview ─────────────────────────────────────────────────

class DataTypeStatus(BaseModel):
    total_records: int = 0
    stock_count: int = 0
    latest_date: Optional[str] = None
    earliest_date: Optional[str] = None


class DataStatusOverview(BaseModel):
    valuations: DataTypeStatus
    financials: DataTypeStatus
    klines: DataTypeStatus
    dividends: DataTypeStatus


# ── Sync trigger ─────────────────────────────────────────────────────────

class SyncTriggerRequest(BaseModel):
    stock_codes: Optional[list[str]] = None  # None = all watched stocks
    years: int = 5


class PipelineStartRequest(BaseModel):
    """Validated body for POST /api/data-management/pipeline/{type}/start.

    Constraints enforced here (entry-point) so manager / pipeline layers can
    trust the values without re-checking. granularity is the financials-only
    toggle: 'y' (annual, default) or 'q' (quarterly)."""
    stock_codes: Optional[list[str]] = None
    force_full: bool = False
    years: int = Field(default=5, ge=1, le=20)
    granularity: Optional[Literal["y", "q"]] = None



# ── Data cleanup ─────────────────────────────────────────────────────────

class CleanupRequest(BaseModel):
    stock_codes: Optional[list[str]] = None  # None = all
    before_date: Optional[str] = None
    after_date: Optional[str] = None


class CleanupPreview(BaseModel):
    data_type: str
    record_count: int
    date_range: Optional[str] = None


class CleanupResult(BaseModel):
    data_type: str
    deleted_count: int