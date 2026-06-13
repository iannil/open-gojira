"""HistoricalFinancial — quarterly/annual financials with publish_date.

report_date is the actual disclosure date (S0.2 spike confirmed Lixinger
exposes this field). Critical for point-in-time correctness in backtest:
on day D, only financials with report_date <= D are "known".
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


class HistoricalFinancial(Base):
    __tablename__ = "historical_financials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_code: Mapped[str] = mapped_column(
        String, ForeignKey("stocks.code"), nullable=False
    )
    period: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    """财报期截止日 (e.g. 2024-12-31 for annual, 2024-09-30 for Q3)."""

    report_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    """实际披露日. From Lixinger's reportDate field."""

    report_type: Mapped[str | None] = mapped_column(String, nullable=True)
    """annual_report | semi_annual_report | first_quarterly_report |
    third_quarterly_report"""

    # Income statement
    revenue: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    operating_profit: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Balance sheet
    total_assets: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_liabilities: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_equity: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Cash flow
    operating_cash_flow: Mapped[float | None] = mapped_column(Float, nullable=True)
    investing_cash_flow: Mapped[float | None] = mapped_column(Float, nullable=True)
    financing_cash_flow: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Ratios
    roe: Mapped[float | None] = mapped_column(Float, nullable=True)
    roa: Mapped[float | None] = mapped_column(Float, nullable=True)
    debt_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    ocf_to_np_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    gross_margin: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "stock_code", "period", name="uq_hist_fin_code_period"
        ),
        Index(
            "ix_historical_financials_code_period", "stock_code", "period"
        ),
    )
