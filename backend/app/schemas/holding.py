"""Pydantic schemas for the portfolio (holdings) module."""

from datetime import date
from typing import Optional

from pydantic import BaseModel


class HoldingCreate(BaseModel):
    """Schema for creating a new holding."""

    stock_code: str
    buy_date: date
    buy_price: float
    quantity: int
    stop_profit_price: float
    sell_date: Optional[date] = None
    sell_price: Optional[float] = None
    trade_rationale: Optional[str] = None
    sell_thesis: Optional[str] = None


class HoldingUpdate(BaseModel):
    """Schema for partially updating a holding. All fields optional."""

    stock_code: Optional[str] = None
    buy_date: Optional[date] = None
    buy_price: Optional[float] = None
    quantity: Optional[int] = None
    sell_date: Optional[date] = None
    sell_price: Optional[float] = None
    stop_profit_price: Optional[float] = None
    trade_rationale: Optional[str] = None
    sell_thesis: Optional[str] = None


class HoldingResponse(BaseModel):
    """Schema for returning a holding with enriched fields."""

    id: int
    stock_code: str
    stock_name: Optional[str] = None
    stock_industry: Optional[str] = None
    buy_date: Optional[str] = None
    buy_price: float
    quantity: int
    sell_date: Optional[str] = None
    sell_price: Optional[float] = None
    stop_profit_price: float
    trade_rationale: Optional[str] = None
    sell_thesis: Optional[str] = None
    current_value: Optional[float] = None
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    annualized_return_pct: Optional[float] = None
    weight_pct: Optional[float] = None

    model_config = {"from_attributes": True}


class SellRequest(BaseModel):
    """Schema for selling a holding."""

    sell_date: date
    sell_price: float
    sell_thesis: Optional[str] = None


class RebalancingItem(BaseModel):
    """A single holding's rebalancing assessment."""

    stock_code: str
    stock_name: Optional[str] = None
    stock_industry: Optional[str] = None
    pnl_pct: Optional[float] = None
    weight_pct: Optional[float] = None
    hold_days: Optional[int] = None
    signal: str  # "green" | "yellow" | "red"
    suggestion: str


class RebalancingGuideResponse(BaseModel):
    """Response schema for the rebalancing guide."""

    holdings: list[RebalancingItem]
    industry_warnings: list[str]
    summary: str


class PortfolioSummary(BaseModel):
    """Schema for portfolio summary with aggregated metrics."""

    total_cost: float
    total_value: float
    total_pnl: float | None = None
    total_pnl_pct: float | None = None
    position_count: int
    holdings: list[HoldingResponse]
    warnings: list[str]
    cash_reserve: float = 0.0
    cash_ratio_pct: float = 0.0
    portfolio_weighted_dyr: float | None = None
    target_weighted_dyr: float = 0.045
    portfolio_annualized_pct: float | None = None


class ThemeBucket(BaseModel):
    theme: str
    value: float
    count: int
    weight_pct: float
    stock_codes: list[str]


class PositionPlanBracket(BaseModel):
    pe_pct_min: float
    pe_pct_max: float
    target_position_pct: float


class PositionPlanResponse(BaseModel):
    plan: list[PositionPlanBracket]
    current_index_pe_pct: float | None = None


class PositionPlanUpsert(BaseModel):
    plan: list[PositionPlanBracket] | None = None
    current_index_pe_pct: float | None = None


class PositionPlanEvaluation(BaseModel):
    current_index_pe_pct: float | None
    current_position_pct: float
    target_position_pct: float | None
    matched_bracket: PositionPlanBracket | None
    gap_pct: float | None
    gap_amount: float | None
    action: str
    plan: list[PositionPlanBracket]
    total_value: float
    cash_reserve: float
    grand_total: float


class AvailableQuantityResponse(BaseModel):
    """T+1 available / frozen / total share counts for a single stock."""

    code: str
    available: int
    frozen: int
    total: int
