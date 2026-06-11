"""Schemas for the cashflow-goal singleton."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class CashflowGoalUpdate(BaseModel):
    annual_expense: Optional[float] = Field(default=None, ge=0)
    goal_multiple: Optional[float] = Field(default=None, gt=0)
    currency: Optional[str] = None
    notes: Optional[str] = None
    cash_reserve: Optional[float] = Field(default=None, ge=0)


class CashflowGoalResponse(BaseModel):
    annual_expense: float
    goal_multiple: float
    currency: str
    notes: Optional[str] = None
    cash_reserve: float = 0.0
    target_annual_cashflow: float
    """annual_expense × goal_multiple — 持仓需要每年产出多少被动现金流。"""
    updated_at: Optional[datetime] = None
