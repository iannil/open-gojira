"""Response schemas for review and backfill endpoints."""

from typing import Optional

from pydantic import BaseModel


class ReviewResponse(BaseModel):
    """Review data — structure varies by period, allow extra fields."""
    model_config = {"extra": "allow"}
    period: Optional[str] = None


class BackfillSuggestionResponse(BaseModel):
    """Draft backfill suggestion — fields vary by suggestion type."""
    model_config = {"extra": "allow"}
    action: str
    message: Optional[str] = None
