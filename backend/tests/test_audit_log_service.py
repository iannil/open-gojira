"""Tests for audit_log_service — the autopilot's black box.

Covers write (flush-based insert with payload serialization), recent (filtered
queries with ordering), and edge cases (payload None, truncation).
"""

from datetime import datetime, timezone

import pytest

from app.models.audit_log import AuditLog
from app.services import audit_log_service


def test_write_basic(db_session):
    """write() inserts a row and assigns an id."""
    row = audit_log_service.write(
        db_session,
        entity_type="trade",
        event="created",
        summary="BUY 600519 100 shares",
        actor="user",
        stock_code="600519",
        payload={"price": 150.0, "quantity": 100},
    )
    assert row.id is not None
    assert row.entity_type == "trade"
    assert row.event == "created"
    assert row.actor == "user"
    assert row.stock_code == "600519"
    assert row.summary == "BUY 600519 100 shares"

    # Verify it's queryable
    saved = db_session.query(AuditLog).filter(AuditLog.id == row.id).first()
    assert saved is not None
    assert saved.entity_type == "trade"


def test_write_no_payload(db_session):
    """write() handles None payload — stores None in DB."""
    row = audit_log_service.write(
        db_session,
        entity_type="system",
        event="startup",
        summary="System started",
    )
    assert row.id is not None
    assert row.payload is None


def test_write_summary_truncated(db_session):
    """summary longer than 500 chars is truncated."""
    long_summary = "x" * 1000
    row = audit_log_service.write(
        db_session,
        entity_type="debug",
        event="long",
        summary=long_summary,
    )
    assert len(row.summary) == 500
    assert row.summary == "x" * 500


def test_recent_returns_newest_first(db_session):
    """recent() orders by created_at desc, id desc."""
    for i in range(5):
        audit_log_service.write(
            db_session,
            entity_type="test",
            event="batch",
            summary=f"entry-{i}",
        )
    db_session.commit()

    rows = audit_log_service.recent(db_session, limit=10)
    assert len(rows) == 5
    summaries = [r.summary for r in rows]
    assert summaries == ["entry-4", "entry-3", "entry-2", "entry-1", "entry-0"]


def test_recent_filters_by_entity_type(db_session):
    """recent() with entity_type filter returns only matching rows."""
    for et in ("trade", "draft", "trade"):
        audit_log_service.write(
            db_session,
            entity_type=et,
            event="created",
            summary=f"type-{et}",
        )
    db_session.commit()

    rows = audit_log_service.recent(db_session, entity_type="trade")
    assert len(rows) == 2
    assert all(r.entity_type == "trade" for r in rows)


def test_recent_filters_by_stock_code(db_session):
    """recent() with stock_code filter returns only matching rows."""
    for sc in ("600519", "000858", "600519"):
        audit_log_service.write(
            db_session,
            entity_type="trade",
            event="created",
            summary=f"stock-{sc}",
            stock_code=sc,
        )
    db_session.commit()

    rows = audit_log_service.recent(db_session, stock_code="600519")
    assert len(rows) == 2


def test_recent_filters_by_event(db_session):
    """recent() with event filter returns only matching rows."""
    audit_log_service.write(db_session, entity_type="draft", event="created", summary="created")
    audit_log_service.write(db_session, entity_type="draft", event="executed", summary="executed")
    audit_log_service.write(db_session, entity_type="draft", event="cancelled", summary="cancelled")
    db_session.commit()

    rows = audit_log_service.recent(db_session, event="executed")
    assert len(rows) == 1
    assert rows[0].event == "executed"


def test_recent_respects_limit(db_session):
    """recent() returns at most `limit` rows."""
    for i in range(20):
        audit_log_service.write(
            db_session,
            entity_type="test",
            event="bulk",
            summary=f"bulk-{i}",
        )
    db_session.commit()

    rows = audit_log_service.recent(db_session, limit=5)
    assert len(rows) == 5


def test_recent_no_match_returns_empty(db_session):
    """recent() returns empty list when no row matches."""
    rows = audit_log_service.recent(db_session, stock_code="NONEXIST")
    assert rows == []


def test_write_with_payload_serialization(db_session):
    """write() serializes dict payload to JSON string."""
    payload = {"reason": "测试", "values": [1, 2, 3]}
    row = audit_log_service.write(
        db_session,
        entity_type="debug",
        event="payload",
        summary="payload test",
        payload=payload,
    )
    assert row.payload is not None
    import json
    parsed = json.loads(row.payload)
    assert parsed["reason"] == "测试"
    assert parsed["values"] == [1, 2, 3]
