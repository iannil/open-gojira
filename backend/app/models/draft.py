"""Draft model — actionable buy/sell suggestion.

v2 (2026-06-24): plan_id FK removed (plans table dropped).
Phase 5 (2026-06-25): draft_generator fields added (decision 9/10 + §7) —
research_report_id / target_price / strategy_tier / sizing_logic /
thesis_status / expires_at / price_ranges_json / serenity_thesis.
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
from sqlalchemy.types import JSON

from app.db.base import Base
from app.core.datetime_utils import now


class Draft(Base):
    __tablename__ = "drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    """v2: kept as plain int (no FK). Will be repurposed in Phase 5."""
    code: Mapped[str] = mapped_column(
        String, ForeignKey("stocks.code"), nullable=False, index=True
    )

    side: Mapped[str] = mapped_column(String, nullable=False)  # BUY | SELL
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="pending", index=True
    )  # pending | executed | cancelled | superseded

    step_kind: Mapped[str] = mapped_column(String, nullable=False)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)

    add_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    reduce_pct_of_position: Mapped[float | None] = mapped_column(Float, nullable=True)

    suggested_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)

    reason: Mapped[str] = mapped_column(Text, nullable=False)

    source: Mapped[str] = mapped_column(String, nullable=False, default="evaluator")

    # ── Phase 5 draft_generator fields (decision 9/10 + §7) ────────────────
    research_report_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    target_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    strategy_tier: Mapped[str | None] = mapped_column(String, nullable=True)  # aggressive | steady
    sizing_logic: Mapped[str | None] = mapped_column(Text, nullable=True)
    thesis_status: Mapped[str | None] = mapped_column(String, nullable=True)  # healthy | invalidated
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    # §7 dual-thesis: ai-berkshire 三策略价格区间 + serenity 卡点论证 (theme picks)
    price_ranges_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    serenity_thesis: Mapped[str | None] = mapped_column(Text, nullable=True)

    triggered_at: Mapped[datetime] = mapped_column(
        DateTime, default=now(), index=True
    )
    executed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_drafts_idempotent", "plan_id", "code", "step_kind", "step_index", "status"),
    )
