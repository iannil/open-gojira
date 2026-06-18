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

    Config consumed by app.services.backtest_engine.run_backtest:
      - stock_codes: universe
      - start_date / end_date: YYYY-MM-DD
      - initial_capital: cash to start with (default 1_000_000)
      - slippage_bps: slippage in basis points (default 10)
      - strategies: list of strategy IDs (filter AND-wise; empty = no signals)
      - target_pct: per-BUY fraction of cash (default 0.10)
    """
    stock_codes: list[str] = Field(..., min_length=1)
    start_date: str  # YYYY-MM-DD
    end_date: str    # YYYY-MM-DD
    initial_capital: float = 1000000.0
    slippage_bps: int = 10
    # F21 (2026-06-18): schema field name must match what backtest_engine reads.
    # Previous field was `strategy_rules: list[dict]` but engine reads
    # `config.get("strategies", [])` as list[int] strategy IDs → permanent
    # mismatch meant all backtests ran with 0 strategies → 0 trades.
    strategies: list[int] = Field(default_factory=list)
    target_pct: float = 0.10


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
