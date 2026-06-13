"""Pydantic schemas for Cash API."""

from datetime import datetime

from pydantic import BaseModel, Field


class CashBalanceResponse(BaseModel):
    balance: float
    as_of_at: datetime
    last_trade_id: int | None
    last_adjustment_id: int | None

    model_config = {"from_attributes": True}


class CashAdjustmentCreate(BaseModel):
    amount: float  # + for deposit, - for withdrawal
    happened_at: datetime
    reason: str = Field(..., pattern="^(deposit|withdrawal|dividend|other)$")
    note: str | None = None


class CashAdjustmentResponse(BaseModel):
    id: int
    amount: float
    happened_at: datetime
    reason: str
    note: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
