"""Eval Set — LLM quality baseline tracking.

EvalRuns capture the output of key LLM pipelines (quality_screen, deep_research)
on a fixed set of stocks. Comparing runs detects prompt drift and
performance regression over time.
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base
from app.core.datetime_utils import now


class EvalRun(Base):
    """A single evaluation run — runs all target pipelines on the eval stock list."""

    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    label: Mapped[str] = mapped_column(String, nullable=False, comment="Human-readable label, e.g. '2026-06-26 baseline'")
    status: Mapped[str] = mapped_column(String, nullable=False, default="running", comment="running | completed | failed")
    pipeline_type: Mapped[str] = mapped_column(String, nullable=False, comment="quality_screen | deep_research")
    stock_count: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class EvalRunItem(Base):
    """Per-stock result within an EvalRun."""

    __tablename__ = "eval_run_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    eval_run_id: Mapped[int] = mapped_column(Integer, ForeignKey("eval_runs.id"), nullable=False, index=True)
    stock_code: Mapped[str] = mapped_column(String, nullable=False)
    stock_name: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending", comment="pending | completed | failed | skipped")
    score: Mapped[float | None] = mapped_column(Float, nullable=True, comment="quality_screen score or deep_research rating")
    score_label: Mapped[str | None] = mapped_column(String, nullable=True, comment="Human-readable score label")
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    conflict_count: Mapped[int] = mapped_column(Integer, default=0)
    red_line_triggered: Mapped[bool] = mapped_column(default=False)
    output_summary: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Short summary of the LLM output")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now())
