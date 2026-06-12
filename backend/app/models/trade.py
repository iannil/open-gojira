"""Trade model — immutable event source for all position changes.

A trade is a fact: at ``filled_at``, N shares of ``stock_code`` were bought/sold
at ``price``, incurring ``commission + stamp_duty + transfer_fee``.

Trades are NEVER updated or deleted. To reverse a trade, create a new trade
of the opposite side with ``reversed_by_trade_id`` pointing back.

Side semantics:
- BUY: quantity > 0, total_value > 0 (cash outflow)
- SELL: quantity < 0, total_value > 0 (cash inflow, but stored as positive number
        representing gross proceeds; net cash = total_value - fees already deducted)
- DIVIDEND: quantity = 0, total_value < 0 (negative = cash inflow)
- CORP_ACTION: quantity = +/-N for stock dividend/capitalization, price = 0
- REVERSAL: opposite of original, points back via reversed_by_trade_id

Total value convention:
- BUY: total_value = price*qty + commission + stamp_duty + transfer_fee
- SELL: total_value = price*qty - commission - stamp_duty - transfer_fee
- DIVIDEND: total_value = -(per_share * qty_held), negative
- CORP_ACTION: total_value = 0 (no cash impact)
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


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_code: Mapped[str] = mapped_column(
        String, ForeignKey("stocks.code"), nullable=False, index=True
    )
    side: Mapped[str] = mapped_column(String, nullable=False, index=True)
    """BUY | SELL | DIVIDEND | CORP_ACTION | REVERSAL"""

    price: Mapped[float] = mapped_column(Float, nullable=False)
    """Per-share price. 0 for corp_action / dividend."""
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    """Signed: +N for incoming, -N for outgoing. DIVIDEND uses 0."""

    filled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    """Trade execution time, Asia/Shanghai (stored as naive datetime)."""

    commission: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    stamp_duty: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    transfer_fee: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_value: Mapped[float] = mapped_column(Float, nullable=False)
    """Net cash impact. See module docstring for sign conventions."""

    source: Mapped[str] = mapped_column(String, nullable=False, default="manual")
    """manual | csv_import | broker_api | corp_action | migration | reversal"""
    source_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    """Draft ID / corp_action ID / migration batch ID."""

    fee_source: Mapped[str] = mapped_column(String, nullable=False, default="auto")
    """auto (computed from broker config) | manual_override"""

    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    reversed_by_trade_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("trades.id"), nullable=True
    )
    """If set, this trade was reversed by the referenced trade."""

    __table_args__ = (
        Index("ix_trades_code_filled", "stock_code", "filled_at"),
        Index("ix_trades_source", "source"),
    )
