"""Execution trace report generator.

Reads JSONL observability log files and produces human-readable call trees,
error summaries, and performance reports for LLM consumption.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.core.observability import _OBS_LOG_DIR

from app.schemas.observability import (
    ErrorEntry,
    SlowSpan,
    SpanEntry,
    TraceReport,
)


def _find_log_files(minutes: int | None = None) -> list[Path]:
    """Return observability log files, optionally filtered by recency."""
    if not _OBS_LOG_DIR.exists():
        return []
    files = sorted(_OBS_LOG_DIR.glob("obs-*.jsonl"))
    if minutes is None:
        return files
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    recent: list[Path] = []
    for f in files:
        try:
            date_str = f.stem.replace("obs-", "")
            file_date = datetime.strptime(date_str, "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
            if file_date >= cutoff:
                recent.append(f)
        except ValueError:
            continue
    return recent


def _read_events(
    files: list[Path], trace_id: str | None = None
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for f in files:
        try:
            with open(f, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if trace_id and event.get("trace_id") != trace_id:
                        continue
                    events.append(event)
        except OSError:
            continue
    return events


def generate_trace_report(trace_id: str) -> TraceReport:
    """Build a TraceReport from log files for a given trace_id."""
    files = _find_log_files(minutes=1440)
    events = _read_events(files, trace_id=trace_id)

    spans: list[SpanEntry] = []
    error_count = 0
    total_duration: float | None = None

    for e in events:
        span = SpanEntry(
            span_id=e.get("span_id", ""),
            parent_span_id=e.get("parent_span_id", ""),
            function=e.get("function", ""),
            event=e.get("event", ""),
            duration_ms=e.get("duration_ms"),
            args=e.get("args"),
            return_type=e.get("return_type"),
            return_summary=e.get("return_summary") or e.get("return_value"),
            error_type=e.get("error_type"),
            error_message=e.get("error_message"),
            ts=e.get("ts"),
        )
        spans.append(span)
        if e.get("event") == "Error":
            error_count += 1
        if e.get("event") == "HTTP_Response" and total_duration is None:
            total_duration = e.get("duration_ms")

    tree_text = _build_tree(spans)

    return TraceReport(
        trace_id=trace_id,
        spans=spans,
        total_duration_ms=total_duration,
        error_count=error_count,
        tree_text=tree_text,
    )


def find_errors(minutes: int = 30) -> list[ErrorEntry]:
    """Find all error events in the last N minutes."""
    files = _find_log_files(minutes=minutes)
    events = _read_events(files)
    errors: list[ErrorEntry] = []
    for e in events:
        if e.get("event") not in ("Error", "Job_Error", "Unhandled_Exception"):
            continue
        errors.append(
            ErrorEntry(
                trace_id=e.get("trace_id", ""),
                span_id=e.get("span_id", ""),
                function=e.get("function", e.get("job_id", "")),
                error_type=e.get("error_type", "Unknown"),
                error_message=e.get("error_message", ""),
                ts=e.get("ts", ""),
                duration_ms=e.get("duration_ms"),
            )
        )
    return errors


def find_slow_spans(
    threshold_ms: float = 1000, minutes: int = 60
) -> list[SlowSpan]:
    """Find spans that exceeded the duration threshold."""
    files = _find_log_files(minutes=minutes)
    events = _read_events(files)
    slow: list[SlowSpan] = []
    for e in events:
        if e.get("event") != "Function_End":
            continue
        dur = e.get("duration_ms", 0)
        if dur and dur >= threshold_ms:
            slow.append(
                SlowSpan(
                    trace_id=e.get("trace_id", ""),
                    span_id=e.get("span_id", ""),
                    function=e.get("function", ""),
                    duration_ms=dur,
                    ts=e.get("ts", ""),
                )
            )
    return slow


def _build_tree(spans: list[SpanEntry]) -> str:
    """Build a text-based call tree from spans."""
    if not spans:
        return "(no spans found)"

    # Use Function_End for tree nodes (they have duration), Error for error nodes
    span_map: dict[str, SpanEntry] = {}
    children: dict[str, list[str]] = defaultdict(list)
    roots: list[str] = []

    for s in spans:
        if s.event == "Function_Start":
            span_map[s.span_id] = s
        elif s.event == "Function_End":
            span_map[s.span_id] = s
        elif s.event == "Error":
            span_map[s.span_id] = s

    # Build parent-child relationships from Function_Start entries
    for s in spans:
        if s.event == "Function_Start":
            pid = s.parent_span_id
            if pid and pid in span_map:
                if s.span_id not in children[pid]:
                    children[pid].append(s.span_id)
            else:
                if s.span_id not in roots:
                    roots.append(s.span_id)

    lines: list[str] = []

    def _render(sid: str, prefix: str = "", is_last: bool = True):
        span = span_map.get(sid)
        if not span:
            return

        connector = "└── " if is_last else "├── "
        dur = f" ({span.duration_ms:.1f}ms)" if span.duration_ms else ""
        err = f" ⚠ {span.error_type}" if span.error_type else ""

        label = span.function or span.event
        if span.event == "Error":
            label = f"ERROR: {span.function}"

        lines.append(f"{prefix}{connector}{label}{dur}{err}")

        child_prefix = prefix + ("    " if is_last else "│   ")
        kids = children.get(sid, [])
        for i, child_id in enumerate(kids):
            _render(child_id, child_prefix, is_last=(i == len(kids) - 1))

    for i, root_id in enumerate(roots):
        _render(root_id, "", is_last=(i == len(roots) - 1))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main():
    """CLI: python -m app.core.observability_report [--trace ID] [--errors MIN] [--slow MS]"""
    import argparse

    parser = argparse.ArgumentParser(description="Observability report tool")
    parser.add_argument("--trace", help="Trace ID to look up")
    parser.add_argument("--errors", type=int, metavar="MINUTES", help="Find errors in last N minutes")
    parser.add_argument("--slow", type=float, metavar="MS", help="Find slow spans (threshold ms)")
    parser.add_argument("--minutes", type=int, default=60, help="Time window for errors/slow (default: 60)")

    args = parser.parse_args()

    if args.trace:
        report = generate_trace_report(args.trace)
        print(f"\n=== Trace Report: {report.trace_id} ===")
        print(f"Duration: {report.total_duration_ms}ms | Errors: {report.error_count} | Spans: {len(report.spans)}")
        print()
        print(report.tree_text)
        print()
        for s in report.spans:
            if s.event == "Error":
                print(f"  ERROR in {s.function}: {s.error_type}: {s.error_message}")
        if not report.spans:
            print("(no events found for this trace)")
    elif args.errors is not None:
        errors = find_errors(minutes=args.errors or 30)
        print(f"\n=== Errors in last {args.errors or 30} minutes: {len(errors)} ===")
        for e in errors:
            print(f"  [{e.ts}] {e.function}: {e.error_type}: {e.error_message}")
    elif args.slow is not None:
        slow = find_slow_spans(threshold_ms=args.slow, minutes=args.minutes)
        print(f"\n=== Slow spans (>={args.slow}ms in last {args.minutes}min): {len(slow)} ===")
        for s in slow:
            print(f"  [{s.ts}] {s.function}: {s.duration_ms:.1f}ms")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
