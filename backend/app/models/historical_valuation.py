"""HistoricalValuation — daily time-series of valuation metrics per stock.

Populated by S4B.2 historical_data_pipeline. Used by S4C backtest engine
for strategy rule evaluation (e.g. PE分位≤30% historical).

Distinct from `valuations` table (which only stores latest snapshot).
"""
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


class HistoricalValuation(Base):
    __tablename__ = "historical_valuations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_code: Mapped[str] = mapped_column(
        String, ForeignKey("stocks.code"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)

    pe_ttm: Mapped[float | None] = mapped_column(Float, nullable=True)
    pb: Mapped[float | None] = mapped_column(Float, nullable=True)
    pb_wo_gw: Mapped[float | None] = mapped_column(Float, nullable=True)
    ps_ttm: Mapped[float | None] = mapped_column(Float, nullable=True)
    pcf_ttm: Mapped[float | None] = mapped_column(Float, nullable=True)
    dyr: Mapped[float | None] = mapped_column(Float, nullable=True)
    sp: Mapped[float | None] = mapped_column(Float, nullable=True)
    mc: Mapped[float | None] = mapped_column(Float, nullable=True)
    mc_om: Mapped[float | None] = mapped_column(Float, nullable=True)
    cmc: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (
        UniqueConstraint("stock_code", "date", name="uq_hist_val_code_date"),
        Index("ix_historical_valuations_code_date", "stock_code", "date"),
    )
