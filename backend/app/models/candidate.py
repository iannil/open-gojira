"""Candidate model — auto-managed screening result.

A Candidate is a stock that currently passes a Plan's strategy criteria.
The plan_runner creates/removes candidates during each scan. Users can pin
candidates (prevent auto-removal) or promote them to the watchlist.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.plan import Plan
    from app.models.stock import Stock


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("plans.id"), nullable=False, index=True
    )
    stock_code: Mapped[str] = mapped_column(
        String, ForeignKey("stocks.code"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="active", index=True
    )
    """'active' | 'removed' | 'promoted'"""
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_confirmed_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    removed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_eval_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Per-strategy evaluation details: {strategy_id: {passed, details}}"""
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    plan: Mapped["Plan"] = relationship(back_populates="candidates")
    stock: Mapped["Stock"] = relationship()
