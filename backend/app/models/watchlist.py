from datetime import datetime
from typing import TYPE_CHECKING, List

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.core.datetime_utils import now

if TYPE_CHECKING:
    pass


class WatchlistGroup(Base):
    __tablename__ = "watchlist_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now())

    items: Mapped[List["WatchlistItem"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (UniqueConstraint("group_id", "stock_code", name="uq_watchlist_group_stock"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("watchlist_groups.id", ondelete="CASCADE"), nullable=False
    )
    stock_code: Mapped[str] = mapped_column(String, ForeignKey("stocks.code"), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_candidate_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("candidates.id"), nullable=True
    )
    """Set when promoted from candidate pool."""
    added_at: Mapped[datetime] = mapped_column(DateTime, default=now())

    group: Mapped["WatchlistGroup"] = relationship(back_populates="items")
