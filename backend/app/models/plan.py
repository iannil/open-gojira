"""Plan model — unified screening + trading plan.

A Plan combines multiple Strategies (screening) with optional trading rules
(buy/sell ladders). Running a plan scans its scope, updates the candidate pool,
and optionally evaluates trading rules for candidates already in the watchlist.

`is_builtin=True` rows are seeded at startup and cannot be edited or deleted.
"""

from datetime import datetime
from typing import TYPE_CHECKING, List

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.candidate import Candidate
    from app.models.draft import Draft


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="active", index=True
    )
    """'active' | 'paused' | 'archived'"""

    # --- Screening configuration ---
    strategy_composition_json: Mapped[str] = mapped_column(Text, nullable=False)
    """JSON: {strategy_ids: [1,2], logic: AND|OR}"""
    scan_scope_json: Mapped[str] = mapped_column(Text, nullable=False)
    """JSON: {type: all_stocks|industries|index|watchlist|custom, values: [...]}"""
    schedule_cron: Mapped[str] = mapped_column(
        String, nullable=False, default="0 18 * * 1-5"
    )

    # --- Trading rules (optional) ---
    trading_rules_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    """JSON: {gates, buy_ladder, sell_ladder, invalidation, cooldown_days}"""

    # --- G2 midstream filter toggle ---
    disable_midstream_filter: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    """G2 (invest3 §13): when False (default), plan_runner filters out stocks
    whose BusinessPattern.is_midstream=True AND Stock.is_cost_leader != True.
    Plan-level逃生口: set True to bypass for special-case plans."""

    # --- M2 in_circle filter toggle (Batch 5 2026-06-17, default flipped 2026-06-18) ---
    disable_in_circle_filter: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    """M2 (invest3 第四层 + 核心十诫 #9 坚守边界): when False, plan_runner
    filters out stocks whose Stock.in_circle=False (用户未标记为"在我的能力
    圈内").

    **Default flipped to True (2026-06-18 audit F12)**: 原默认 False 在
    Stock.in_circle 字段从未填充的情况下排除 100% 股票,plan_runner 永远
    产出 0 候选。改为默认 True (filter 关),用户主动标 in_circle 后再
    opt-in 启用 filter (设为 False)。"""

    # --- G1 cycle gate ---
    cycle_buy_max: Mapped[str] = mapped_column(
        String, nullable=False, default="mid", server_default="mid"
    )
    """G1 (invest3 §5): max cycle position at which BUY drafts may be emitted.
    Enum: extreme_low / low / mid / high / extreme_high.
    Default 'mid' = block when market is high/extreme_high. Set 'extreme_high' to disable."""

    # --- Run state ---
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_run_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    """JSON: {passed: N, failed: N, drafts: N, errors: [...]}"""

    # --- Metadata ---
    is_builtin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, onupdate=func.now(), nullable=True
    )

    # --- Relationships ---
    candidates: Mapped[List["Candidate"]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
        lazy="select",
    )
    drafts: Mapped[List["Draft"]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
        lazy="select",
    )
