"""Research run — single execution of serenity-skill workflow."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.core.datetime_utils import now


class ResearchRun(Base):
    """A single serenity research execution.

    Lifecycle: running → completed / failed.
    One row per run; structured children live in 5 child tables
    (value_chain_layers / scarce_layers / research_company_universe /
    research_evidence / research_company_ranking).

    Q8 cost tracking fields: llm_token_input / llm_token_output / llm_search_count.
    """

    __tablename__ = "research_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    research_theme_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("research_themes.id"), nullable=False, index=True
    )

    status: Mapped[str] = mapped_column(String, nullable=False, default="running")
    # "running" / "completed" / "failed"

    # ── Scope ────────────────────────────────────────────────────────────
    scope_market: Mapped[str] = mapped_column(String, nullable=False)
    scope_time_window: Mapped[str] = mapped_column(
        String, nullable=False, default="3-12M"
    )
    triggered_by: Mapped[str] = mapped_column(
        String, nullable=False, default="manual"
    )
    # "manual" / "scheduler"

    # ── LLM config & usage (Q8 cost tracking) ────────────────────────────
    llm_provider: Mapped[str] = mapped_column(
        String, nullable=False, default="glm-4.7"
    )
    llm_token_input: Mapped[int] = mapped_column(Integer, default=0)
    llm_token_output: Mapped[int] = mapped_column(Integer, default=0)
    llm_search_count: Mapped[int] = mapped_column(Integer, default=0)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # ── Structured result summaries (children hold details) ─────────────
    system_change_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_conditions_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_steps_md: Mapped[str | None] = mapped_column(Text, nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime] = mapped_column(DateTime, default=now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
