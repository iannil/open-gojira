"""Pydantic schemas for the dividend tracking module."""

from datetime import date
from typing import Optional

from pydantic import BaseModel


class DividendRecordCreate(BaseModel):
    """Schema for creating a dividend record."""

    stock_code: str
    ex_date: date
    amount_per_share: float
    quantity_held: int
    total_received: float
    reinvested: bool = False


class DividendRecordUpdate(BaseModel):
    """Schema for updating a dividend record. All fields optional."""

    stock_code: Optional[str] = None
    ex_date: Optional[date] = None
    amount_per_share: Optional[float] = None
    quantity_held: Optional[int] = None
    total_received: Optional[float] = None
    reinvested: Optional[bool] = None


class DividendRecordResponse(BaseModel):
    """Schema for returning a dividend record with enriched stock_name."""

    id: int
    stock_code: str
    stock_name: Optional[str] = None
    ex_date: Optional[str] = None
    amount_per_share: float
    quantity_held: int
    total_received: float
    reinvested: Optional[bool] = None
    created_at: Optional[str] = None

    model_config = {"from_attributes": True}


class DividendYearSummary(BaseModel):
    """Summary of dividends received in a given year."""

    year: int
    total_received: float
    count: int


class DividendStockSummary(BaseModel):
    """Summary of dividends received for a given stock."""

    stock_code: str
    stock_name: Optional[str] = None
    total_received: float
    count: int
    annual_yield: Optional[float] = None


class DividendSummaryResponse(BaseModel):
    """Aggregated dividend summary across all records."""

    total_cumulative: float
    by_year: list[DividendYearSummary]
    by_stock: list[DividendStockSummary]
