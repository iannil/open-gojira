from datetime import date, datetime
from typing import TYPE_CHECKING, List

from sqlalchemy import Date, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.dividend import DividendRecord
    from app.models.holding import Holding
    from app.models.valuation import ValuationSnapshot


class Stock(Base):
    __tablename__ = "stocks"

    code: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    industry: Mapped[str | None] = mapped_column(String, nullable=True)
    listed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    qiu_score: Mapped[int] = mapped_column(Integer, default=0)
    security_theme: Mapped[str | None] = mapped_column(String, nullable=True)
    """安全主线：能源 / 粮食 / 金融 / 资源 / 科技 / 信息 / 民生 / None"""
    quadrant: Mapped[str | None] = mapped_column(String, nullable=True)
    """资产四象限：procyclical | countercyclical | distressed_reversal | financial | None"""
    tier: Mapped[str | None] = mapped_column(String, nullable=True)
    """Investment tier: 'core' (high-certainty core) | 'watch' (satellite) | None"""
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    thesis_variables_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    """JSON string of thesis variables for this stock."""
    qiu_detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    """JSON: {upstream_power: 0|1, downstream_power: 0|1, government_power: 0|1, evidence: {...}}"""
    hq_region: Mapped[str | None] = mapped_column(String, nullable=True)
    """Headquarter region (省/市), used for bank blind-box analysis."""
    # ── Trading-status fields (sourced from Lixinger /cn/company) ──────────
    # These are the raw source values for derived board/ST/suspension detection.
    # Storing raw beats inferring from code prefix or name (S0.6 spike finding).
    listing_status: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    """8-value Lixinger enum: normally_listed | delisting_risk_warning |
    special_treatment | delisting_transitional_period | ipo_suspension |
    issued_but_not_listed | issue_failure | unauthorized."""
    exchange: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    """sh | sz | bj — used with listing_status to derive board/ST/suspended."""
    fs_table_type: Mapped[str | None] = mapped_column(String, nullable=True)
    """non_financial | bank | security | insurance | other_financial.
    Routes per-stock fundamentals/financials to the correct Lixinger endpoint."""
    ipo_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    """IPO date (raw from Lixinger). Distinct from listed_date (legacy)."""
    sync_source: Mapped[str | None] = mapped_column(String, nullable=True, default="manual")
    """How this stock entered the system: manual | bootstrap | delta."""
    delisted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    """When this stock was delisted. Non-NULL = delisted."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, onupdate=func.now(), nullable=True
    )

    # Relationships
    valuations: Mapped[List["ValuationSnapshot"]] = relationship(
        back_populates="stock", cascade="all, delete-orphan"
    )
    holdings: Mapped[List["Holding"]] = relationship(
        back_populates="stock", cascade="all, delete-orphan"
    )
    dividends: Mapped[List["DividendRecord"]] = relationship(
        back_populates="stock", cascade="all, delete-orphan"
    )
