"""BacktestRun — record of a single backtest execution.

Lifecycle: pending → running → completed | failed

config_json stores the immutable input parameters at run creation.
result_json (filled on completion) stores metrics + equity curve +
trade summary for UI visualization.
"""
from datetime import datetime
from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    config_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    """Input: strategy_ids, plan_id, start_date, end_date,
    initial_capital, slippage_bps, lot_size, etc."""

    status: Mapped[str] = mapped_column(String, nullable=False, default="pending", index=True)
    """pending | running | completed | failed"""

    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    """Output: metrics (cagr/sharpe/maxDD/win_rate), equity_curve,
    monthly_returns, trades_count, signals_count, benchmark_comparison."""

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
