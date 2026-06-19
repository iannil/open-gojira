"""Cash adjustment — non-trade cash flows (deposit / withdrawal / other).

Used when cash changes for reasons other than trade execution:
- User deposits fresh capital
- User withdraws cash
- Dividend cash received outside the trade stream (rare; usually modeled
  as a DIVIDEND-side trade)
- Correction entries

Each row is an immutable log entry. Writing an adjustment should also
update ``cash_balance`` inside the same transaction (see cash_service).
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.core.datetime_utils import now


class CashAdjustment(Base):
    __tablename__ = "cash_adjustments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    amount: Mapped[float] = mapped_column(Float, nullable=False)
    """Signed: + for deposit/inflow, - for withdrawal/outflow."""

    happened_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    """When the adjustment occurred (user-entered). Indexed for range queries."""

    reason: Mapped[str] = mapped_column(String, nullable=False)
    """deposit | withdrawal | dividend | other"""

    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Free-form description (e.g. '月度入金', '应急取现')."""

    created_at: Mapped[datetime] = mapped_column(DateTime, default=now())
    """When this row was inserted into the DB."""
