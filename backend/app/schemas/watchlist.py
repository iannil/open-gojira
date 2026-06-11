from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class WatchlistItemCreate(BaseModel):
    stock_code: str
    note: Optional[str] = None


class WatchlistItemUpdate(BaseModel):
    note: Optional[str] = None


class WatchlistItemResponse(BaseModel):
    id: int
    group_id: int
    stock_code: str
    stock_name: Optional[str] = None
    note: Optional[str] = None
    added_at: Optional[str] = None

    model_config = {"from_attributes": True}


class WatchlistGroupCreate(BaseModel):
    name: str
    description: Optional[str] = None
    sort_order: int = 0


class WatchlistGroupUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None


class WatchlistGroupResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    sort_order: int = 0
    items: list[WatchlistItemResponse] = []
    created_at: Optional[str] = None

    model_config = {"from_attributes": True}


class WatchlistBulkAdd(BaseModel):
    group_id: int
    stock_codes: list[str]
