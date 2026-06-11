"""Pydantic schemas for the valuation module."""

from typing import Optional

from pydantic import BaseModel


class PercentileBand(BaseModel):
    percentile: int
    value: float


class DataPoint(BaseModel):
    date: str
    pe_ttm: Optional[float] = None
    pb: Optional[float] = None


class PercentileResponse(BaseModel):
    pe_bands: list[PercentileBand] = []
    pb_bands: list[PercentileBand] = []
    current_pe: Optional[float] = None
    current_pb: Optional[float] = None
    current_pe_percentile: Optional[float] = None
    current_pb_percentile: Optional[float] = None
    data_points: list[DataPoint] = []


class ValuationSnapshotResponse(BaseModel):
    id: int
    stock_code: str
    date: Optional[str] = None
    pe_ttm: Optional[float] = None
    pb: Optional[float] = None
    pe_percentile_10y: Optional[float] = None
    pb_percentile_10y: Optional[float] = None
    dividend_yield: Optional[float] = None
    created_at: Optional[str] = None

    model_config = {"from_attributes": True}


class SustainabilityResponse(BaseModel):
    status: str
    message: str


class ForwardDyrResponse(BaseModel):
    stock_code: str
    forward_dyr: Optional[float] = None
    payout_ratio_avg_3y: Optional[float] = None
    eps: Optional[float] = None
    current_price: Optional[float] = None
    trailing_dyr: Optional[float] = None
    basis_note: str


class CalculatorPrefillResponse(BaseModel):
    stock_code: str
    report_date: Optional[str] = None
    net_profit_yi: Optional[float] = None
    operating_cash_flow_yi: Optional[float] = None
    dividends_paid_yi: Optional[float] = None
    eps: Optional[float] = None
    payout_ratio_pct: Optional[float] = None
    current_price: Optional[float] = None
    dividend_yield_pct: Optional[float] = None
    annual_dividend_per_share: Optional[float] = None
    growth_rate_pct: Optional[float] = None


class DashboardResponse(BaseModel):
    stock_code: str
    latest_snapshot: Optional[ValuationSnapshotResponse] = None
    snapshots: list[ValuationSnapshotResponse] = []
    sustainability: Optional[SustainabilityResponse] = None
    composite: Optional[dict] = None
    current_pe: Optional[float] = None
    current_pb: Optional[float] = None
    current_price: Optional[float] = None
    dividend_yield: Optional[float] = None
    market_cap: Optional[float] = None
