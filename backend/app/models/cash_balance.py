"""Cash balance — singleton row, updated atomically with each trade.

There is exactly ONE row in this table (id=1). It represents the current
cash position of the investment account. Updates happen inside the same
transaction as trade writes (see trade_service.record_trade).

Sign convention for ``balance``:
- BUY trade: balance -= trade.total_value (total_value > 0, cash outflow)
- SELL trade: balance += trade.total_value (cash inflow)
- DIVIDEND trade: balance += -trade.total_value (total_value < 0, so positive)
- Deposit/withdrawal: balance += cash_adjustment.amount (signed)
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.core.datetime_utils import now


class CashBalance(Base):
    __tablename__ = "cash_balance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    """Always 1. Singleton row."""

    balance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    """Current cash position. Signed: positive = cash available."""

    as_of_at: Mapped[datetime] = mapped_column(
        DateTime, default=now(), nullable=False
    )
    """Last time balance was updated. Refreshed on every trade / adjustment."""

    last_trade_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    """FK to trades.id, set after each trade write. Soft ref (no FK constraint
    to avoid circular dependency with trades table)."""

    last_adjustment_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    """FK to cash_adjustments.id. Soft ref for audit traceability."""
