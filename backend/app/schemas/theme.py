"""Theme schemas — request/response models for the theme router."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ThemeCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    description: str | None = None
    target_weight_pct: float = Field(default=0.0, ge=0.0, le=100.0)


class ThemeUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=50)
    description: str | None = None
    target_weight_pct: float | None = Field(None, ge=0.0, le=100.0)


class ThemeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    target_weight_pct: float
