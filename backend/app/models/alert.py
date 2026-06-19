from datetime import datetime
from typing import List

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.core.datetime_utils import now


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_type: Mapped[str] = mapped_column(String, nullable=False)
    stock_code: Mapped[str | None] = mapped_column(
        String, ForeignKey("stocks.code"), nullable=True
    )
    params: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now())
    last_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    events: Mapped[List["AlertEvent"]] = relationship(
        back_populates="rule", cascade="all, delete-orphan"
    )


class AlertEvent(Base):
    __tablename__ = "alert_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("alert_rules.id", ondelete="CASCADE"), nullable=False
    )
    stock_code: Mapped[str | None] = mapped_column(String, nullable=True)
    rule_type: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    severity: Mapped[str] = mapped_column(String, default="info", nullable=False)
    fired_at: Mapped[datetime] = mapped_column(DateTime, default=now())
    acked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    acked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    rule: Mapped["AlertRule"] = relationship(back_populates="events")
