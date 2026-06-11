"""Schemas for data quality endpoint."""

from typing import Optional

from pydantic import BaseModel, Field


class DataTypeQualityDetails(BaseModel):
    total_stocks: int = 0
    covered_stocks: int = 0
    latest_date: Optional[str] = None
    earliest_date: Optional[str] = None


class DataTypeQuality(BaseModel):
    completeness_rate: float = 0.0
    freshness: str = "missing"  # fresh, stale, missing
    gap_count: int = 0
    anomaly_count: int = 0
    validation_pass_rate: float = 0.0
    details: DataTypeQualityDetails


class DataQualityResponse(BaseModel):
    overall_score: int = 0
    data_types: dict[str, DataTypeQuality] = Field(default_factory=dict)
    recommendations: list[str] = Field(default_factory=list)
