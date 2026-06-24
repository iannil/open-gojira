"""LLM call log — per-call observability (cost/tokens/latency).

Per decision 15: extends @tracked decorator's coverage for LLM-specific fields.
"""
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base
from app.core.datetime_utils import now


class LLMCallLog(Base):
    __tablename__ = "llm_call_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trace_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    span_id: Mapped[str | None] = mapped_column(String, nullable=True)
    model: Mapped[str] = mapped_column(String, nullable=False, index=True)
    pipeline_type: Mapped[str | None] = mapped_column(String, nullable=True)
    stock_code: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    prompt_hash: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    tool_calls_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    conflict_flags_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=now(), index=True
    )
