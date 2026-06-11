"""Monthly review aggregator tests."""

from datetime import date, datetime

import pytest

from app.models.audit_log import AuditLog
from app.services import review_service
from app.services.review_service import MonthWindow
from tests.conftest import TestSessionLocal


@pytest.fixture
def db():
    s = TestSessionLocal()
    try:
        yield s
    finally:
        s.close()


def _add(db, *, when: datetime, **kwargs):
    row = AuditLog(**kwargs)
    db.add(row)
    db.flush()
    # bypass server_default to control timestamps
    row.created_at = when
    db.flush()


def test_month_window_parses_explicit_value():
    win = MonthWindow.parse("2026-06")
    assert win.year == 2026 and win.month == 6
    assert win.start == datetime(2026, 6, 1)
    assert win.end == datetime(2026, 7, 1)
    assert win.label == "2026-06"


def test_month_window_defaults_to_current_month():
    win = MonthWindow.parse(None)
    today = date.today()
    assert win.year == today.year and win.month == today.month


def test_month_window_handles_december_rollover():
    win = MonthWindow.parse("2026-12")
    assert win.end == datetime(2027, 1, 1)


def test_compute_empty_window(db):
    out = review_service.compute(db, year_month="2026-06")
    assert out.month == "2026-06"
    assert out.drafts_triggered == 0
    assert out.hit_rate is None
    assert out.by_stock == []
    assert out.entries == []


def test_compute_counts_drafts_and_hit_rate(db):
    _add(
        db,
        when=datetime(2026, 6, 5, 17, 45),
        entity_type="draft",
        entity_id="1",
        event="triggered",
        actor="evaluator",
        stock_code="601398",
        summary="BUY 601398",
        payload='{"add_pct": 0.05}',
    )
    _add(
        db,
        when=datetime(2026, 6, 6, 9, 30),
        entity_type="draft",
        entity_id="1",
        event="executed",
        actor="user",
        stock_code="601398",
        summary="executed",
    )
    _add(
        db,
        when=datetime(2026, 6, 7, 17, 45),
        entity_type="draft",
        entity_id="2",
        event="triggered",
        actor="evaluator",
        stock_code="600519",
        summary="SELL 600519",
        payload='{"reduce_pct_of_position": 0.5}',
    )
    _add(
        db,
        when=datetime(2026, 6, 8, 10, 0),
        entity_type="draft",
        entity_id="2",
        event="cancelled",
        actor="user",
        stock_code="600519",
        summary="cancelled",
    )
    db.commit()

    out = review_service.compute(db, year_month="2026-06")
    assert out.drafts_triggered == 2
    assert out.drafts_executed == 1
    assert out.drafts_cancelled == 1
    assert out.hit_rate == pytest.approx(0.5)
    assert out.buy_drafts == 1
    assert out.sell_drafts == 1
    by_code = {b["stock_code"] for b in out.by_stock}
    assert by_code == {"601398", "600519"}


def test_compute_counts_plan_and_holding_events(db):
    _add(
        db,
        when=datetime(2026, 6, 1, 9, 0),
        entity_type="plan",
        event="created",
        actor="user",
        stock_code="601398",
        summary="plan created",
    )
    _add(
        db,
        when=datetime(2026, 6, 3, 17, 45),
        entity_type="plan",
        event="invalidated",
        actor="evaluator",
        stock_code="600519",
        summary="invalidated",
    )
    _add(
        db,
        when=datetime(2026, 6, 4, 17, 45),
        entity_type="plan",
        event="status_changed",
        actor="evaluator",
        stock_code="601398",
        summary="armed → partial",
    )
    _add(
        db,
        when=datetime(2026, 6, 5, 10, 0),
        entity_type="holding",
        event="created",
        actor="user",
        stock_code="601398",
        summary="买入 1000 股",
    )
    _add(
        db,
        when=datetime(2026, 6, 28, 10, 0),
        entity_type="holding",
        event="sold",
        actor="user",
        stock_code="601398",
        summary="清仓",
    )
    _add(
        db,
        when=datetime(2026, 6, 10, 22, 0),
        entity_type="cashflow_goal",
        entity_id="1",
        event="updated",
        actor="user",
        summary="goal set",
    )
    db.commit()

    out = review_service.compute(db, year_month="2026-06")
    assert out.plans_created == 1
    assert out.plans_invalidated == 1
    assert out.plans_status_changed == 1
    assert out.holdings_created == 1
    assert out.holdings_sold == 1
    assert out.cashflow_goal_updates == 1


def test_compute_window_excludes_neighboring_months(db):
    _add(
        db,
        when=datetime(2026, 5, 31, 23, 59),
        entity_type="draft",
        event="triggered",
        actor="evaluator",
        stock_code="A",
        summary="last day of May",
    )
    _add(
        db,
        when=datetime(2026, 7, 1, 0, 1),
        entity_type="draft",
        event="triggered",
        actor="evaluator",
        stock_code="B",
        summary="first minute of July",
    )
    _add(
        db,
        when=datetime(2026, 6, 15, 12, 0),
        entity_type="draft",
        event="triggered",
        actor="evaluator",
        stock_code="C",
        summary="june",
    )
    db.commit()

    out = review_service.compute(db, year_month="2026-06")
    assert out.drafts_triggered == 1
    assert {b["stock_code"] for b in out.by_stock} == {"C"}


def test_compute_entry_limit_caps_timeline(db):
    for i in range(15):
        _add(
            db,
            when=datetime(2026, 6, i + 1, 17, 45),
            entity_type="draft",
            event="triggered",
            actor="evaluator",
            stock_code="X",
            summary=f"day-{i}",
        )
    db.commit()
    out = review_service.compute(db, year_month="2026-06", entry_limit=5)
    assert len(out.entries) == 5
    # newest first
    assert out.entries[0]["summary"] == "day-14"
