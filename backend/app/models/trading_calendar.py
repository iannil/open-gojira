"""TradingCalendar — pre-populated with A-share trading holidays.

Seeder includes known holidays for 2025-2027. Update yearly.
is_trading_day() falls back to weekday check for dates not in table.
"""
from datetime import date
from sqlalchemy import Boolean, Date, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TradingCalendar(Base):
    __tablename__ = "trading_calendar"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    is_trading_day: Mapped[bool] = mapped_column(Boolean, nullable=False)
    holiday_name: Mapped[str | None] = mapped_column(String, nullable=True)
    """Human-readable holiday name (e.g. '元旦', '国庆节'), null for normal days."""
