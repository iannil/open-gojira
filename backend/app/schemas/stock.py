from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class ThesisVariable(BaseModel):
    """A thesis variable for a stock."""
    name: str
    current_value: Optional[float] = None
    target_condition: Optional[str] = None  # e.g. "> 8", "< 5000"
    unit: Optional[str] = None
    source: Optional[str] = "manual"


class StockCreate(BaseModel):
    code: str
    name: Optional[str] = None
    auto_fetch: bool = True


class StockUpdate(BaseModel):
    name: Optional[str] = None
    industry: Optional[str] = None
    listed_date: Optional[date] = None
    qiu_score: Optional[int] = Field(default=None, ge=0, le=3)
    security_theme: Optional[str] = None
    tier: Optional[str] = None
    notes: Optional[str] = None


class StockResponse(BaseModel):
    code: str
    name: str
    industry: Optional[str] = None
    listed_date: Optional[date] = None
    quadrant: Optional[str] = None
    qiu_score: int = 0
    qiu_detail: Optional[dict] = None
    security_theme: Optional[str] = None
    tier: Optional[str] = None
    notes: Optional[str] = None
    thesis_variables: Optional[list[dict]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    analysis_count: int = 0
    latest_valuation_date: Optional[date] = None

    model_config = {"from_attributes": True}


class ShareholderRecord(BaseModel):
    date: Optional[str] = None
    holder_name: Optional[str] = None
    holder_type: Optional[str] = None
    holding_quantity: Optional[float] = None
    holding_ratio: Optional[float] = None


class NorthFlowRecord(BaseModel):
    date: str
    net_buy_amount: Optional[float] = None
    holding_quantity: Optional[float] = None
    holding_ratio: Optional[float] = None


class MarginTradingRecord(BaseModel):
    date: str
    financing_balance: Optional[float] = None
    securities_balance: Optional[float] = None
    net_financing: Optional[float] = None


class UniverseItem(BaseModel):
    code: str
    name: str
    tier: Optional[str] = None
    security_theme: Optional[str] = None
    industry: Optional[str] = None
    qiu_score: int = 0
    has_plan: bool = False
    plan_status: Optional[str] = None
    candidate_count: int = 0
    is_held: bool = False
    weight_pct: Optional[float] = None
    latest_pe_pct: Optional[float] = None
    latest_dyr: Optional[float] = None


class FullUniverseItem(BaseModel):
    code: str
    name: str
    industry: Optional[str] = None
    latest_pe_pct: Optional[float] = None
    latest_pb_pct: Optional[float] = None
    latest_dyr: Optional[float] = None
    latest_pe_ttm: Optional[float] = None
    latest_pb: Optional[float] = None


class FullUniverseResponse(BaseModel):
    items: list[FullUniverseItem]
    total: int
    page: int
    page_size: int


class UniverseCoverageStats(BaseModel):
    total_stocks: int = 0
    valuation_coverage: int = 0
    coverage_pct: float = 0.0
    mode: str = "manual"


class QiuScoreInput(BaseModel):
    upstream_power: int = Field(ge=0, le=1)
    downstream_power: int = Field(ge=0, le=1)
    government_power: int = Field(ge=0, le=1)
    evidence: dict = {}


class SyncResult(BaseModel):
    total_fetched: int
    inserted: int
    updated: int
    skipped: int
    industry_updated: int = 0
