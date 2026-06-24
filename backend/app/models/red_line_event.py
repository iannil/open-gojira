"""Red line event — 8 red line triggers.

Per decision 13: hard reject triggers that prevent stock from entering candidate pool.
"""
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base
from app.core.datetime_utils import now


# Red line types (8 条红线)
RED_LINE_MANAGEMENT_INTEGRITY = "management_integrity"
RED_LINE_FINANCIAL_FRAUD = "financial_fraud"
RED_LINE_MAJOR_VIOLATION = "major_violation"
RED_LINE_CONSECUTIVE_LOSSES = "consecutive_losses"
RED_LINE_HIGH_PLEDGE = "high_pledge"
RED_LINE_FREQUENT_REDUCTION = "frequent_reduction"
RED_LINE_COMPLEX_RELATED_TRANSACTIONS = "complex_related_transactions"
RED_LINE_BENFORD_ANOMALY = "benford_anomaly"

ALL_RED_LINES = {
    RED_LINE_MANAGEMENT_INTEGRITY,
    RED_LINE_FINANCIAL_FRAUD,
    RED_LINE_MAJOR_VIOLATION,
    RED_LINE_CONSECUTIVE_LOSSES,
    RED_LINE_HIGH_PLEDGE,
    RED_LINE_FREQUENT_REDUCTION,
    RED_LINE_COMPLEX_RELATED_TRANSACTIONS,
    RED_LINE_BENFORD_ANOMALY,
}


class RedLineEvent(Base):
    __tablename__ = "red_line_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_code: Mapped[str] = mapped_column(
        String, ForeignKey("stocks.code"), nullable=False, index=True
    )
    red_line_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    report_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    severity: Mapped[str] = mapped_column(String, nullable=False, default="hard_reject")
    evidence_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    action_taken: Mapped[str] = mapped_column(String, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=now(), index=True)
