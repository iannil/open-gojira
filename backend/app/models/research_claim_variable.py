"""Research claim variable — LLM-proposed thesis monitor variable (v2 Phase 2 #9 阶段 B).

Each row = one proposed monitor derived from a ResearchClaim's signal field.
LLM analyzes claim.signal ("净息差<1.3%持续两个季度") and outputs:

  - variable_name: human-readable metric name ("净息差")
  - threshold_critical: numeric breach threshold (1.3)
  - breach_when: "lt" | "gt" — 字面对齐 signal 文本比较符
  - source: routing key for fetcher ("financial:NIM" / "valuation:PE_percentile" / ...)
  - window_periods: optional, N 期连续 breach 才告警 (null=单点)

State machine: proposed → active (approve) | rejected (reject).
Active vars are checked nightly by thesis_monitor_service.check_claim_variables.

v2 Q4'-C: research_claim_variables is the sole source of truth for claim-derived
monitors; we do NOT copy to Stock.thesis_variables_json. The latter stays the
domain of thesis_variable_sync_service (template-driven sync).
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.core.datetime_utils import now


class ResearchClaimVariable(Base):
    """One LLM-proposed monitor variable tied to a research_claim row."""

    __tablename__ = "research_claim_variables"
    __table_args__ = (
        # v2 Q-new: DB-level guard against same claim re-proposing same var
        # (business-level dedup is the primary mechanism, this is a backstop)
        # Note: SQLite ignores partial constraints; we still emit it for Postgres.
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    research_claim_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("research_claims.id"), nullable=False, index=True
    )
    stock_code: Mapped[str] = mapped_column(
        String, ForeignKey("stocks.code"), nullable=False, index=True
    )

    # ── LLM-proposed structured fields ────────────────────────────────
    variable_name: Mapped[str] = mapped_column(Text, nullable=False)
    # e.g. "净息差" / "毛利率" / "PE 分位"

    threshold_critical: Mapped[float] = mapped_column(Float, nullable=False)

    breach_when: Mapped[str] = mapped_column(String, nullable=False)
    # v2: "lt" | "gt" — 字面对齐 signal 文本比较符
    # signal "净息差<1.3%" → breach_when="lt", threshold_critical=1.3
    # signal "不良率突破2%" → breach_when="gt", threshold_critical=2.0
    # monitor: breach_when="lt" → alert when value < threshold
    #          breach_when="gt" → alert when value > threshold

    unit: Mapped[str | None] = mapped_column(String, nullable=True)
    # "%" / "倍" / null

    source: Mapped[str] = mapped_column(String, nullable=False)
    # routing key into thesis_monitor_service._fetch_<source>
    # e.g. "financial:NIM" / "valuation:PE_percentile" / "kline:price_drop_52w"

    window_periods: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # null or 1 = single-point check; ≥2 = require consecutive N periods breach

    # ── State machine ─────────────────────────────────────────────────
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="proposed", index=True
    )
    # "proposed" | "active" | "rejected"

    proposed_at: Mapped[datetime] = mapped_column(
        DateTime, default=now()
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String, nullable=True)
    # personal tool — always "user" when set
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # free-form note from approve/reject/edit

    # ── Monitor dedup ─────────────────────────────────────────────────
    last_alerted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # v2 Q6'-B1: 7-day dedup window. null = never alerted.

    def __repr__(self) -> str:
        return (
            f"<ResearchClaimVariable id={self.id} "
            f"claim={self.research_claim_id} stock={self.stock_code} "
            f"{self.variable_name} {self.breach_when} {self.threshold_critical}>"
        )
