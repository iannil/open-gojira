"""Response schemas for market endpoints."""

from typing import Optional

from pydantic import BaseModel


class IndexKlinePoint(BaseModel):
    """Single K-line data point for index."""
    model_config = {"extra": "allow"}
    date: Optional[str] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[float] = None


class IndexKlineResponse(BaseModel):
    """Index K-line response with stock code and points array."""
    model_config = {"extra": "allow"}
    stock_code: Optional[str] = None
    points: list[IndexKlinePoint] = []


class CycleAssessmentResponse(BaseModel):
    """Market cycle assessment — fields from dataclass.to_dict(), allow extra."""
    model_config = {"extra": "allow"}
    temperature: Optional[float] = None
    stage: Optional[str] = None


class DividendProjectionResponse(BaseModel):
    """Dividend projection — fields vary, allow extra."""
    model_config = {"extra": "allow"}


class ThesisAlertResponse(BaseModel):
    """Thesis alert item — fields vary, allow extra."""
    model_config = {"extra": "allow"}
