from typing import Optional

from pydantic import BaseModel


class FinancialStatementResponse(BaseModel):
    id: int
    stock_code: str
    report_date: str
    report_type: str
    revenue: Optional[float] = None
    revenue_growth: Optional[float] = None
    net_profit: Optional[float] = None
    net_profit_growth: Optional[float] = None
    gross_margin: Optional[float] = None
    net_margin: Optional[float] = None
    eps_basic: Optional[float] = None
    total_assets: Optional[float] = None
    total_liabilities: Optional[float] = None
    shareholders_equity: Optional[float] = None
    current_ratio: Optional[float] = None
    debt_ratio: Optional[float] = None
    goodwill: Optional[float] = None
    total_shares: Optional[float] = None
    operating_cash_flow: Optional[float] = None
    investing_cash_flow: Optional[float] = None
    financing_cash_flow: Optional[float] = None
    free_cash_flow: Optional[float] = None
    ocf_to_profit_ratio: Optional[float] = None
    roe: Optional[float] = None
    roa: Optional[float] = None
    dividend_payout_ratio: Optional[float] = None
    dividends_paid: Optional[float] = None
    npl_ratio: Optional[float] = None
    provision_coverage_ratio: Optional[float] = None
    net_interest_margin: Optional[float] = None
    core_tier1_car: Optional[float] = None

    model_config = {"from_attributes": True}


class RatioDataPoint(BaseModel):
    date: str
    roe: Optional[float] = None
    roa: Optional[float] = None
    gross_margin: Optional[float] = None
    net_margin: Optional[float] = None
    debt_ratio: Optional[float] = None
    ocf_to_profit_ratio: Optional[float] = None
    revenue_growth: Optional[float] = None
    net_profit_growth: Optional[float] = None


class RatioTrendResponse(BaseModel):
    stock_code: str
    annual: list[RatioDataPoint]
    quarterly: list[RatioDataPoint]


class PeerData(BaseModel):
    stock_code: str
    stock_name: str
    roe: Optional[float] = None
    roa: Optional[float] = None
    gross_margin: Optional[float] = None
    debt_ratio: Optional[float] = None
    pe_ttm: Optional[float] = None
    pb: Optional[float] = None


class PeerComparisonResponse(BaseModel):
    stock_code: str
    industry: Optional[str] = None
    peers: list[PeerData]


class AnomalyItem(BaseModel):
    severity: str  # "high", "medium", "low"
    title: str
    detail: str
    metric: Optional[str] = None


class AnomalyResponse(BaseModel):
    stock_code: str
    anomalies: list[AnomalyItem]


