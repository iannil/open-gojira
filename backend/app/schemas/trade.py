"""Pydantic schemas for Trade API."""

from datetime import datetime

from pydantic import BaseModel, Field


class TradeCreate(BaseModel):
    """Manual trade entry from UI."""

    stock_code: str = Field(..., min_length=1, max_length=20)
    side: str = Field(..., pattern="^(BUY|SELL|DIVIDEND|CORP_ACTION)$")
    price: float = Field(..., gt=0)
    quantity: int = Field(..., gt=0)
    filled_at: datetime
    source: str = Field(default="manual", pattern="^(manual|csv_import|broker_api)$")
    source_ref: str | None = None
    commission_override: float | None = Field(default=None, ge=0)
    note: str | None = None


class TradeResponse(BaseModel):
    id: int
    stock_code: str
    side: str
    price: float
    quantity: int
    filled_at: datetime
    commission: float
    stamp_duty: float
    transfer_fee: float
    total_value: float
    source: str
    source_ref: str | None
    fee_source: str
    note: str | None
    created_at: datetime
    reversed_by_trade_id: int | None

    model_config = {"from_attributes": True}


class TradeListResponse(BaseModel):
    items: list[TradeResponse]
    total: int
