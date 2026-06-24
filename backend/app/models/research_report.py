"""Research report — LLM Pipeline output (JSON + Markdown).

Per decision 6: each Pipeline run produces both structured JSON (feeds next
Pipeline) and Markdown (human-readable ai-berkshire style report).
"""
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base
from app.core.datetime_utils import now


# Pipeline types
PIPELINE_DEEP_RESEARCH = "deep_research"
PIPELINE_THESIS_TRACKER = "thesis_tracker"
PIPELINE_NEWS_PULSE = "news_pulse"
PIPELINE_EARNINGS_REVIEW = "earnings_review"
PIPELINE_QUALITY_SCREEN = "quality_screen"

# Report status
STATUS_COMPLETED = "completed"
STATUS_REJECTED = "rejected"      # red line hit
STATUS_CONFLICT = "conflict"      # data conflict > threshold
STATUS_STALE = "stale"            # expired

# Recommendations
REC_BUY = "BUY"
REC_HOLD = "HOLD"
REC_PASS = "PASS"
REC_SELL = "SELL"
REC_TRIM = "TRIM"


class ResearchReport(Base):
    __tablename__ = "research_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_code: Mapped[str] = mapped_column(
        String, ForeignKey("stocks.code"), nullable=False, index=True
    )
    pipeline_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    json_output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    markdown_output: Mapped[str | None] = mapped_column(Text, nullable=True)

    evidence_grade: Mapped[str | None] = mapped_column(String(1), nullable=True)  # A/B/C
    data_conflict_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    red_line_hit_json: Mapped[list | None] = mapped_column(JSON, nullable=True)

    prompt_version: Mapped[str | None] = mapped_column(String, nullable=True)
    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    recommendation: Mapped[str | None] = mapped_column(String, nullable=True)

    status: Mapped[str] = mapped_column(
        String, nullable=False, default=STATUS_COMPLETED
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=now(), index=True)
