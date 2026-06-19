"""HoldingRiskRule — stop-loss / take-profit rules per position.

One rule per stock_code (since holdings are derived from trades).
Triggered rules record timestamp + reason; reset manually if user
re-evaluates after partial close.
"""
from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.core.datetime_utils import now


class HoldingRiskRule(Base):
    __tablename__ = "holding_risk_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_code: Mapped[str] = mapped_column(
        String, ForeignKey("stocks.code"), nullable=False, unique=True, index=True
    )
    """One rule per stock (holdings derived from trades, not per Holding row)."""

    stop_loss_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    """E.g. 0.08 = -8% triggers stop loss."""
    stop_loss_type: Mapped[str] = mapped_column(
        String, nullable=False, default="pct_from_cost"
    )
    """pct_from_cost | fixed_price | trailing"""

    take_profit_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit_type: Mapped[str] = mapped_column(
        String, nullable=False, default="pct_from_cost"
    )

    peak_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    """For trailing stop: highest price seen since rule active."""

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    trigger_reason: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
