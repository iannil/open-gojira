"""Observability query API endpoints."""

from fastapi import APIRouter

from app.core.observability_report import (
    find_errors,
    find_slow_spans,
    generate_trace_report,
)
from app.schemas.observability import (
    RecentErrorsResponse,
    SlowSpansResponse,
    TraceReport,
)

router = APIRouter(prefix="/observability", tags=["observability"])


@router.get("/trace/{trace_id}", response_model=TraceReport)
def get_trace(trace_id: str):
    return generate_trace_report(trace_id)


@router.get("/recent-errors", response_model=RecentErrorsResponse)
def get_recent_errors(minutes: int = 30):
    errors = find_errors(minutes=minutes)
    return RecentErrorsResponse(errors=errors, total=len(errors))


@router.get("/slow-spans", response_model=SlowSpansResponse)
def get_slow_spans(threshold_ms: float = 1000, minutes: int = 60):
    spans = find_slow_spans(threshold_ms=threshold_ms, minutes=minutes)
    return SlowSpansResponse(spans=spans, total=len(spans), threshold_ms=threshold_ms)


@router.get("/events")
def get_event_registry():
    from app.core.events import bus
    reg = bus.get_registry()
    return {
        "events": {
            et.__name__: handlers
            for et, handlers in reg.items()
        },
        "total_event_types": len(reg),
        "total_handlers": sum(len(hs) for hs in reg.values()),
    }
