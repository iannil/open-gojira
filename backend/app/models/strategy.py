"""Strategy model — atomic, reusable screening rule.

A Strategy evaluates a single stock against a set of conditions (rule_json)
and returns pass/fail. Strategies are composed into Plans via
strategy_composition_json.

`is_builtin=True` rows are seeded at startup and cannot be edited or deleted.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.core.datetime_utils import now


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    kind: Mapped[str] = mapped_column(String, nullable=False, default="custom")
    """'builtin' | 'custom'"""
    rule_json: Mapped[str] = mapped_column(Text, nullable=False)
    """Declarative rule DSL: {logic: AND|OR, conditions: [{field, op, value}]}"""
    is_builtin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, onupdate=func.now(), nullable=True
    )
