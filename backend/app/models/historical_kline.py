"""HistoricalKline — daily OHLCV for backtesting."""
from datetime import date

from sqlalchemy import (
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class HistoricalKline(Base):
    __tablename__ = "historical_klines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_code: Mapped[str] = mapped_column(
        String, ForeignKey("stocks.code"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)

    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    """成交额 (volume × price)."""
    turnover_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    """换手率, from Lixinger's to_r field (volume may be null per S0.3 spike)."""

    __table_args__ = (
        UniqueConstraint("stock_code", "date", name="uq_hist_kline_code_date"),
        Index("ix_historical_klines_code_date", "stock_code", "date"),
    )
