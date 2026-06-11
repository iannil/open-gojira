"""Schemas for data management endpoints."""

from datetime import date, datetime
from typing import Optional

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