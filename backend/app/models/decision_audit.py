"""Decision audit — Tier 2 metrics (P&L tracking for approved drafts).

Per decision 16: tracks approved drafts' 30/90/365-day P&L for quality measurement.
"""
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.core.datetime_utils import now


class DecisionAudit(Base):
    __tablename__ = "decision_audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    draft_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String, nullable=True)

    stock_code: Mapped[str] = mapped_column(String, nullable=False, index=True)
    action: Mapped[str] = mapped_column(String, nullable=False)  # BUY | SELL | TRIM

    target_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    executed_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status_30d: Mapped[str | None] = mapped_column(String, nullable=True)  # gain | loss | flat
    status_90d: Mapped[str | None] = mapped_column(String, nullable=True)
    status_365d: Mapped[str | None] = mapped_column(String, nullable=True)
    benchmark_diff_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    thesis_status_now: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now(), onupdate=now())
