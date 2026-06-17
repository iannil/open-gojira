"""M2 (Batch 5 2026-06-17): invest3 第四层 + 核心十诫 #9 坚守边界 —
Stock.in_circle filter at plan_runner scan stage.

Verifies:
1. Stock with in_circle=False is filtered out (no candidate, no draft)
2. Stock with in_circle=True passes through normally
3. plan.disable_in_circle_filter=True bypasses (escape hatch)
"""
from __future__ import annotations

import json as _json
from datetime import date, datetime

from app.models.cash_balance import CashBalance
from app.models.plan import Plan
from app.models.stock import Stock
from app.models.strategy import Strategy
from app.models.valuation import ValuationSnapshot
from app.services.plan_runner import run_plan, _filter_out_of_circle


def _make_strategy(db) -> int:
    """Trivial-pass strategy that always succeeds (rule with no conditions)."""
    s = Strategy(
        name="trivial-pass",
        slug=f"trivial-pass-{datetime.now().strftime('%H%M%S%f')}",
        description="",
        kind="custom",
        rule_json=_json.dumps({
            "logic": "AND",
            "conditions": [{"field": "pe_pct_10y", "op": "<=", "value": 100}],
        }),
        is_builtin=False,
    )
    db.add(s)
    db.flush()
    return s.id


def _make_plan(db, slug: str, *, strategy_id: int, disable_in_circle: bool = False) -> Plan:
    plan = Plan(
        name=f"test-{slug}",
        slug=f"test-{slug}-{datetime.now().strftime('%H%M%S%f')}",
        status="active",
        scan_scope_json='{"type":"custom","values":["600519","600000"]}',
        strategy_composition_json=_json.dumps({
            "strategy_ids": [strategy_id],
            "logic": "AND",
        }),
        disable_in_circle_filter=disable_in_circle,
    )
    db.add(plan)
    db.flush()
    return plan


def _seed_stock(db, code: str, *, in_circle: bool) -> None:
    today = date.today()
    db.add(Stock(
        code=code, name=f"测试 {code}", exchange="sh",
        listing_status="normally_listed", prev_close=100.0,
        industry="白酒",
        in_circle=in_circle,
    ))
    db.add(ValuationSnapshot(
        stock_code=code, date=today,
        dividend_yield=0.05,
        pe_percentile_10y=30.0,
        pb_percentile_10y=20.0,
        pe_ttm=20.0, pb=3.0,
    ))


def _seed_freshness(db) -> None:
    """Bypass plan_runner's freshness gate (stocks + valuation both gate)."""
    from app.services.data_freshness_service import record_sync_success as _rss
    _rss(db, "stocks", record_count=2)
    _rss(db, "valuation", record_count=2)
    db.flush()


class TestM2InCircleFilterUnit:
    def test_filter_returns_kept_and_dropped_count(self, db_session):
        db = db_session
        _seed_stock(db, "600519", in_circle=True)
        _seed_stock(db, "600000", in_circle=False)
        db.flush()

        kept, dropped = _filter_out_of_circle(db, ["600519", "600000"])
        assert kept == ["600519"]
        assert dropped == 1

    def test_filter_empty_input(self, db_session):
        kept, dropped = _filter_out_of_circle(db_session, [])
        assert kept == []
        assert dropped == 0


class TestM2InCircleFilterIntegration:
    def test_filter_logs_count_in_run_summary(self, db_session):
        """plan_runner.last_run_summary contains filtered_out_of_circle count."""
        db = db_session
        sid = _make_strategy(db)
        _seed_stock(db, "600519", in_circle=True)
        _seed_stock(db, "600000", in_circle=False)
        db.add(CashBalance(id=1, balance=1_000_000.0))
        _seed_freshness(db)

        plan = _make_plan(db, "filter-active", strategy_id=sid)
        result = run_plan(db, plan)

        assert result.filtered_out_of_circle == 1
        assert result.scanned == 2

    def test_escape_hatch_disables_filter(self, db_session):
        """plan.disable_in_circle_filter=True bypasses M2 filter entirely."""
        db = db_session
        sid = _make_strategy(db)
        _seed_stock(db, "600519", in_circle=False)
        _seed_stock(db, "600000", in_circle=False)
        db.add(CashBalance(id=1, balance=1_000_000.0))
        _seed_freshness(db)

        plan = _make_plan(db, "escape", strategy_id=sid, disable_in_circle=True)
        result = run_plan(db, plan)

        assert result.filtered_out_of_circle == 0
        assert result.scanned == 2
