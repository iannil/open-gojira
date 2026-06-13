"""Pydantic schemas for BacktestRun API.

The router currently defines request/response models inline (v1 — small
surface). These schemas are exported here so other modules / future
front-end integration can import them without depending on the router.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class BacktestSubmit(BaseModel):
    """Payload for POST /api/backtests.

    strategy_rules format (v1, simplified):
        [{metric, operator, threshold, action, target_pct}]
    See app.services.backtest_engine docstring for full spec.
    """
    stock_codes: list[str] = Field(..., min_length=1)
    start_date: str  # YYYY-MM-DD
    end_date: str    # YYYY-MM-DD
    initial_capital: float = 1000000.0
    slippage_bps: int = 10
    strategy_rules: list[dict] = Field(default_factory=list)


class BacktestResponse(BaseModel):
    id: int
    status: str
    config_json: dict[str, Any]
    result_json: dict[str, Any] | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}
