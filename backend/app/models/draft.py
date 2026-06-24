"""Draft model — actionable buy/sell suggestion.

v2 (2026-06-24): plan_id FK removed (plans table dropped). New fields will be
added in Phase 5 (trigger_source, strategy_tier, sizing_logic, expires_at).
"""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.core.datetime_utils import now


class Draft(Base):
    __tablename__ = "drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    """v2: kept as plain int (no FK). Will be repurposed in Phase 5."""
    code: Mapped[str] = mapped_column(
        String, ForeignKey("stocks.code"), nullable=False, index=True
    )

    side: Mapped[str] = mapped_column(String, nullable=False)  # BUY | SELL
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="pending", index=True
    )  # pending | executed | cancelled | superseded

    step_kind: Mapped[str] = mapped_column(String, nullable=False)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)

    add_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    reduce_pct_of_position: Mapped[float | None] = mapped_column(Float, nullable=True)

    suggested_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)

    reason: Mapped[str] = mapped_column(Text, nullable=False)

    source: Mapped[str] = mapped_column(String, nullable=False, default="evaluator")

    triggered_at: Mapped[datetime] = mapped_column(
        DateTime, default=now(), index=True
    )
    executed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_drafts_idempotent", "plan_id", "code", "step_kind", "step_index", "status"),
    )
