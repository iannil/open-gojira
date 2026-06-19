from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.core.datetime_utils import now


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
    # D3 (2026-06-17 invest-alignment audit): 财报红旗字段 (invest1 §三 + invest2 §10)
    # Lixinger metric keys (best-effort, may need API verification):
    #   accounts_receivable: bs.ar.t | inventory: bs.inv.t | inventory_turnover: m.i_tor.t
    #   non_recurring_profit_ratio: ps.np_wd_s_r.t (扣非净利率, 经验值)
    accounts_receivable: Mapped[float | None] = mapped_column(Float, nullable=True)
    """应收账款 (Lixinger bs.ar.t, 已 spike 验证 2026-06-17). 用于红旗: 应收增速 >> 营收增速 = 伪造销售嫌疑."""
    inventory: Mapped[float | None] = mapped_column(Float, nullable=True)
    """存货 (Lixinger 不提供 bs.inv.t, 字段保留以备未来数据源). 始终 None."""
    inventory_turnover_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    """存货周转率 (Lixinger m.i_tor.t, 已 spike 验证 2026-06-17). 用于红旗: 同比骤降."""
    non_recurring_profit_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    """扣非净利率 (Lixinger 不提供 ps.np_wd_s_r.t, 字段保留). 始终 None."""
    audit_opinion: Mapped[str | None] = mapped_column(String, nullable=True)
    """审计意见 (Lixinger auditOpinionType top-level field, 已 spike 验证 2026-06-17).
    值: standard_unqualified (unqualified_opinion) / qualified / adverse / disclaimer.
    用于红旗: 非标准审计意见 = 财报可信度疑问."""
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now())


