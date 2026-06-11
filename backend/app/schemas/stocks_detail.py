"""Response schemas for stock detail endpoints."""

from typing import Any, Optional

from pydantic import BaseModel


class ShareholdersNumRecord(BaseModel):
    date: Optional[str] = None
    shareholders_num: Optional[int] = None
    avg_holding_value: Optional[float] = None


class ThesisTemplatesResponse(BaseModel):
    industry: Optional[str] = None
    templates: list[dict[str, Any]] = []
