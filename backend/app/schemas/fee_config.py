"""Pydantic schemas for BrokerFeeConfig API."""

from datetime import date

from pydantic import BaseModel, Field


class BrokerFeeConfigCreate(BaseModel):
    broker_name: str = Field(..., min_length=1, max_length=100)
    commission_rate: float = Field(..., gt=0, lt=0.01)  # max 1%
    commission_min: float = Field(..., ge=0)
    stamp_duty_rate: float = Field(..., ge=0, lt=0.01)
    transfer_fee_rate: float = Field(..., ge=0, lt=0.01)
    effective_from: date
    is_active: bool = True


class BrokerFeeConfigUpdate(BaseModel):
    commission_rate: float | None = Field(default=None, gt=0, lt=0.01)
    commission_min: float | None = Field(default=None, ge=0)
    stamp_duty_rate: float | None = Field(default=None, ge=0, lt=0.01)
    transfer_fee_rate: float | None = Field(default=None, ge=0, lt=0.01)
    is_active: bool | None = None


class BrokerFeeConfigResponse(BaseModel):
    id: int
    broker_name: str
    commission_rate: float
    commission_min: float
    stamp_duty_rate: float
    transfer_fee_rate: float
    effective_from: date
    is_active: bool

    model_config = {"from_attributes": True}
