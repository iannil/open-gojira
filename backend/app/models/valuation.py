from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.core.datetime_utils import now


class ValuationSnapshot(Base):
    __tablename__ = "valuations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_code: Mapped[str] = mapped_column(
        String, ForeignKey("stocks.code"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)

    # Valuation multiples — the canonical snapshot fields. Historical
    # fundamentals (eps/ocf/net_profit/dividends/payout) used to live here
    # but were never populated by any service; the live calculators now
    # read those from FinancialStatement directly via /valuation/{code}/prefill.
    pe_ttm: Mapped[float | None] = mapped_column(Float, nullable=True)
    pb: Mapped[float | None] = mapped_column(Float, nullable=True)
    pe_percentile_10y: Mapped[float | None] = mapped_column(Float, nullable=True)
    pb_percentile_10y: Mapped[float | None] = mapped_column(Float, nullable=True)
    dividend_yield: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=now()
    )

    # Relationships
    stock: Mapped["Stock"] = relationship(back_populates="valuations")  # noqa: F821

    __table_args__ = (
        UniqueConstraint("stock_code", "date", name="uq_valuation_stock_date"),
        Index("ix_valuation_stock_date", "stock_code", "date"),
    )
