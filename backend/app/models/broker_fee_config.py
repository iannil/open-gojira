"""Broker fee configuration — supports historical rate changes.

A-share fees change over time (e.g. stamp duty was 0.1% pre-2023-08-28,
0.05% sell-only from 2023-10-23). This table stores multiple configs with
different effective_from dates. fee_calculator_service picks the right one
based on trade.filled_at.

Only one config should have is_active=True for a given broker at a time
(enforced at app layer, not DB).
"""
from datetime import date

from sqlalchemy import Boolean, Date, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BrokerFeeConfig(Base):
    __tablename__ = "broker_fee_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    broker_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    """Identifier for the broker account (e.g. 'default', '华泰', '同花顺')."""

    commission_rate: Mapped[float] = mapped_column(Float, nullable=False)
    """Commission as fraction of notional (e.g. 0.00025 = 0.025%)."""
    commission_min: Mapped[float] = mapped_column(Float, nullable=False, default=5.0)
    """Minimum commission per trade in CNY (typically 5 元)."""

    stamp_duty_rate: Mapped[float] = mapped_column(Float, nullable=False)
    """Stamp duty as fraction of notional (sell-side only, 0.0005 currently)."""
    transfer_fee_rate: Mapped[float] = mapped_column(Float, nullable=False)
    """Transfer fee as fraction of notional (both sides, 0.00001 currently)."""

    effective_from: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    """Date this rate takes effect."""
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    """Currently in use. Historical configs set to False."""
