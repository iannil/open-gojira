"""BusinessPattern schemas — request/response models for business-patterns router.

Maps to invest docs methodology (invest1/2/3). See models/business_pattern.py for semantics.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ThesisVariableTemplate(BaseModel):
    """One entry in BusinessPattern.thesis_variables_json."""

    name: str
    unit: str | None = None
    source: str = "manual"
    """'manual' = user-entered; 'lixinger' = auto-synced from FinancialStatement."""
    current_value: Any | None = None
    target_condition: str | None = None


class BusinessPatternBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    theme_id: int | None = None
    description: str | None = None
    first_principle_variable: str | None = None
    power_tier_baseline: int = Field(default=0, ge=0, le=3)
    thesis_variables: list[ThesisVariableTemplate] = Field(default_factory=list)
    lixinger_industries: list[str] = Field(default_factory=list)
    source_ref: str | None = None


class BusinessPatternCreate(BusinessPatternBase):
    is_builtin: bool = False
    """User-created patterns are never builtin; the field exists for symmetry."""

    @model_validator(mode="after")
    def _user_created_no_source_ref(self) -> "BusinessPatternCreate":
        # builtin only set via seeder; user-created should not carry source_ref
        if not self.is_builtin and self.source_ref:
            raise ValueError(
                "source_ref is reserved for builtin patterns; clear it for user-created patterns."
            )
        return self


class BusinessPatternUpdate(BaseModel):
    """Partial update. Builtin patterns: only description editable (enforced in service)."""

    name: str | None = Field(None, min_length=1, max_length=80)
    theme_id: int | None = None
    description: str | None = None
    first_principle_variable: str | None = None
    power_tier_baseline: int | None = Field(None, ge=0, le=3)
    thesis_variables: list[ThesisVariableTemplate] | None = None
    lixinger_industries: list[str] | None = None
    source_ref: str | None = None


class BusinessPatternResponse(BusinessPatternBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_builtin: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ThesisTemplateResponse(BaseModel):
    """Response for GET /api/business-patterns/{id}/thesis-templates."""

    pattern_id: int
    pattern_name: str
    templates: list[ThesisVariableTemplate]


class StockBusinessPatternUpdate(BaseModel):
    """Payload for PATCH /api/stocks/{code}/business-pattern (manual override)."""

    business_pattern_id: int | None
    """Null clears the association; non-null sets it (must reference existing pattern)."""
