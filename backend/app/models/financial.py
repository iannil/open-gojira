from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FinancialStatement(Base):
    __tablename__ = "financial_statements"
    # Idempotent upsert key — application-level dedup also enforced in
    # fetch_and_store_financials, but the DB constraint is the durable guard
    # against concurrent inserts and ad-hoc backfills creating duplicates.
    __table_args__ = (
        UniqueConstraint(
            "stock_code", "report_date", "report_type",
            name="uq_financial_stmt_code_date_type",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_code: Mapped[str] = mapped_column(String, nullable=False, index=True)
    report_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    report_type: Mapped[str] = mapped_column(String, nullable=False)  # "annual", "quarterly"
    # Income statement
    revenue: Mapped[float | None] = mapped_column(Float, nullable=True)
    revenue_growth: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_profit_growth: Mapped[float | None] = mapped_column(Float, nullable=True)
    gross_margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    eps_basic: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Balance sheet
    total_assets: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_liabilities: Mapped[float | None] = mapped_column(Float, nullable=True)
    shareholders_equity: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    debt_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    goodwill: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_shares: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Cash flow
    operating_cash_flow: Mapped[float | None] = mapped_column(Float, nullable=True)
    investing_cash_flow: Mapped[float | None] = mapped_column(Float, nullable=True)
    financing_cash_flow: Mapped[float | None] = mapped_column(Float, nullable=True)
    free_cash_flow: Mapped[float | None] = mapped_column(Float, nullable=True)
    ocf_to_profit_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Key ratios
    roe: Mapped[float | None] = mapped_column(Float, nullable=True)
    roa: Mapped[float | None] = mapped_column(Float, nullable=True)
    dividend_payout_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Dividends
    dividends_paid: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Bank-specific metrics
    npl_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    """Non-performing loan ratio (不良贷款率)."""
    provision_coverage_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    """Provision coverage ratio (拨备覆盖率)."""
    net_interest_margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    """Net interest margin (净息差)."""
    core_tier1_car: Mapped[float | None] = mapped_column(Float, nullable=True)
    """Core tier-1 capital adequacy ratio (核心一级资本充足率)."""
    # Raw data for flexibility
    raw_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


