"""Pydantic schemas for observability API endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SpanEntry(BaseModel):
    span_id: str
    parent_span_id: str
    function: str
    event: str
    duration_ms: float | None = None
    args: dict[str, Any] | None = None
    return_type: str | None = None
    return_summary: Any = None
    error_type: str | None = None
    error_message: str | None = None
    ts: str | None = None


class TraceReport(BaseModel):
    trace_id: str
    spans: list[SpanEntry]
    total_duration_ms: float | None = None
    error_count: int = 0
    tree_text: str = ""


class ErrorEntry(BaseModel):
    trace_id: str
    span_id: str
    function: str
    error_type: str
    error_message: str
    ts: str
    duration_ms: float | None = None


class SlowSpan(BaseModel):
    trace_id: str
    span_id: str
    function: str
    duration_ms: float
    ts: str


class RecentErrorsResponse(BaseModel):
    errors: list[ErrorEntry]
    total: int


class SlowSpansResponse(BaseModel):
    spans: list[SlowSpan]
    total: int
    threshold_ms: float
