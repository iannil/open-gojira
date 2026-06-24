"""Stock lifecycle — state machine per stock.

Per decision 17: tracks stock position in the funnel:
universe → watchlist → researched → candidate → signaled → holding → exited
"""
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base
from app.core.datetime_utils import now


# State constants
STATE_UNIVERSE = "universe"
STATE_WATCHLIST = "watchlist"
STATE_RESEARCHED = "researched"
STATE_CANDIDATE = "candidate"
STATE_SIGNALED = "signaled"
STATE_HOLDING = "holding"
STATE_EXITED = "exited"

ALL_STATES = {
    STATE_UNIVERSE, STATE_WATCHLIST, STATE_RESEARCHED,
    STATE_CANDIDATE, STATE_SIGNALED, STATE_HOLDING, STATE_EXITED,
}


class StockLifecycle(Base):
    __tablename__ = "stock_lifecycle"

    stock_code: Mapped[str] = mapped_column(
        String, ForeignKey("stocks.code"), primary_key=True, nullable=False
    )
    current_state: Mapped[str] = mapped_column(String, nullable=False, index=True)
    entered_state_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_research_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    history_json: Mapped[list | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now(), onupdate=now())
