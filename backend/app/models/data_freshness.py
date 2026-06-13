"""DataFreshness — track last sync time per data category.

Categories: stocks / valuation / kline / financial / dividend / corp_action

plan_runner asserts freshness before running (avoid generating drafts
on stale data). Pipelines update this table on success/failure.
"""
from datetime import datetime
from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DataFreshness(Base):
    __tablename__ = "data_freshness"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    """stocks / valuation / kline / financial / dividend / corp_action"""

    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    """Last time sync was attempted (success or failure)."""

    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    """Last time sync completed successfully."""

    last_record_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    """Number of records in last successful sync."""

    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    """Error message from last failure (None if last sync succeeded)."""
