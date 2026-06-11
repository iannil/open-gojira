from typing import Optional

from pydantic import BaseModel


class KlinePoint(BaseModel):
    date: str  # YYYY-MM-DD
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[float] = None


class KlineResponse(BaseModel):
    stock_code: str
    freq: str
    points: list[KlinePoint]


class BandLevel(BaseModel):
    """One quantile band: e.g. low/mid/high of historical PE multiple."""
    label: str  # e.g. "p10", "p50", "p90"
    multiple: float  # the absolute PE / PB value at that quantile


class ValuationBandsResponse(BaseModel):
    stock_code: str
    metric: str  # "pe_ttm" or "pb"
    dates: list[str]
    close: list[Optional[float]]
    actual_multiple: list[Optional[float]]
    # Implied close prices for each band level (same length as dates).
    # implied_close[level] = close[t] * band_multiple / actual_multiple[t]
    band_levels: list[BandLevel]
    implied_close: dict[str, list[Optional[float]]]


class KlineSummaryItem(BaseModel):
    stock_code: str
    stock_name: Optional[str] = None
    earliest_date: Optional[str] = None
    latest_date: Optional[str] = None
    total_bars: Optional[int] = None


class KlineSummaryResponse(BaseModel):
    items: list[KlineSummaryItem] = []
