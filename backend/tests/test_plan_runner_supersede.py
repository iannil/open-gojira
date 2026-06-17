"""Test plan_runner auto-supersede of stale drafts (D 分支 Q18 决策).

When a plan runs, drafts from previous runs that are not re-confirmed
(getting their triggered_at refreshed via draft_service.emit) should be
marked 'superseded'. This keeps the pending pool clean — only drafts
representing current strategy suggestions remain.
"""
from datetime import date, datetime, timedelta
from typing import Generator

import pytest
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, pool

from app.db.base import Base
from app.models.broker_fee_config import BrokerFeeConfig
from app.models.cash_balance import CashBalance
from app.models.candidate import Candidate
from app.models.draft import Draft
from app.models.plan import Plan
from app.models.price_kline import PriceKline
from app.models.stock import Stock
from app.models.strategy import Strategy
from app.models.valuation import ValuationSnapshot
from app.services import draft_service
from app.services.plan_runner import run_plan


# Use a dedicated in-memory engine per test module (the autouse fixture
# in conftest creates/drops all tables per test, but plan_runner.run_plan
# uses SessionLocal internally in some paths — keep it simple here by
# going through db_session fixture that proxies the same engine).

@pytest.fixture
def setup(db_session):
    """Seed: 1 stock + valuation + cash + fee config + freshness."""
    today = date.today()
    db_session.add(Stock(
        code="600519", name="贵州茅台", exchange="sh",
        listing_status="normally_listed", prev_close=100.0,
        industry="白酒",
        in_circle=True,
    ))
    db_session.add(ValuationSnapshot(
        stock_code="600519", date=today,
        dividend_yield=0.05,
        pe_percentile_10y=30.0,
        pb_percentile_10y=20.0,
        pe_ttm=20.0, pb=3.0,
    ))
    db_session.add(PriceKline(
        stock_code="600519", date=today, freq="day",
        open=100, high=101, low=99, close=100, volume=10000,
    ))
    db_session.add(CashBalance(id=1, balance=1_000_000.0))
    db_session.add(BrokerFeeConfig(
        broker_name="default", commission_rate=0.00025, commission_min=5.0,
        stamp_duty_rate=0.0005, transfer_fee_rate=0.00001,
        effective_from=date(2023, 10, 23), is_active=True,
    ))
    from app.services.data_freshness_service import record_sync_success as _rss
    _rss(db_session, "stocks", record_count=1)
    _rss(db_session, "valuation", record_count=1)
    db_session.flush()


def _make_strategy(db_session) -> Strategy:
    import json
    s = Strategy(
        name="trivial-pass", slug="trivial_pass_supersede",
        description="", kind="custom",
        rule_json=json.dumps({
            "logic": "AND",
            "conditions": [{"field": "dyr", "op": ">=", "value": 0.0}],
        }),
        is_builtin=False,
    )
    db_session.add(s)
    db_session.flush()
    return s


def _make_plan(db_session, strategy_id: int, scope_codes: list[str], trading_rules: dict | None = None) -> Plan:
    import json
    plan = Plan(
        name="test-plan", slug="test_plan_supersede", description="",
        status="active",
        strategy_composition_json=json.dumps({
            "strategy_ids": [strategy_id], "logic": "AND",
        }),
        scan_scope_json=json.dumps({"type": "custom", "values": scope_codes}),
        trading_rules_json=json.dumps(trading_rules) if trading_rules else None,
        is_builtin=False,
    )
    db_session.add(plan)
    db_session.flush()
    return plan


def test_supersede_old_pending_draft_when_strategy_no_longer_fires(db_session, setup):
    """Old pending draft + new run that doesn't re-emit → draft marked superseded."""
    s = _make_strategy(db_session)
    rules = {
        "buy_ladder": [
            {"trigger": {"kind": "dyr_ge", "value": 0.04}, "add_pct": 0.10},
        ],
        "sell_ladder": [],
        "invalidation": [],
        "cooldown_days": 0,
    }
    plan = _make_plan(db_session, strategy_id=s.id, scope_codes=["600519"], trading_rules=rules)

    # Run 1: should emit a BUY draft
    r1 = run_plan(db_session, plan)
    db_session.flush()
    assert r1.drafts_emitted >= 1
    pending_after_r1 = db_session.query(Draft).filter_by(plan_id=plan.id, status="pending").all()
    assert len(pending_after_r1) >= 1

    # Simulate time passing — manually age the draft's triggered_at backwards
    old_ts = datetime.utcnow() - timedelta(days=5)
    for d in pending_after_r1:
        d.triggered_at = old_ts
    db_session.flush()

    # Change strategy so it no longer passes (dyr >= 1.0 impossible)
    import json
    s.rule_json = json.dumps({
        "logic": "AND",
        "conditions": [{"field": "dyr", "op": ">=", "value": 1.0}],
    })
    db_session.flush()

    # Run 2: strategy fails → no draft emitted → previous draft should be superseded
    r2 = run_plan(db_session, plan)
    db_session.flush()
    assert r2.drafts_emitted == 0
    assert r2.drafts_superseded >= 1, "Old pending draft should be superseded"

    pending_after_r2 = db_session.query(Draft).filter_by(plan_id=plan.id, status="pending").all()
    assert len(pending_after_r2) == 0, "No pending drafts should remain"
    superseded = db_session.query(Draft).filter_by(plan_id=plan.id, status="superseded").all()
    assert len(superseded) >= 1


def test_freshly_emitted_draft_not_superseded(db_session, setup):
    """When strategy still fires, emit() refreshes triggered_at → not superseded."""
    s = _make_strategy(db_session)
    rules = {
        "buy_ladder": [
            {"trigger": {"kind": "dyr_ge", "value": 0.04}, "add_pct": 0.10},
        ],
        "sell_ladder": [],
        "invalidation": [],
        "cooldown_days": 0,
    }
    plan = _make_plan(db_session, strategy_id=s.id, scope_codes=["600519"], trading_rules=rules)

    # Run 1: emit
    r1 = run_plan(db_session, plan)
    db_session.flush()
    assert r1.drafts_emitted >= 1

    # Run 2: same conditions → re-emit (refresh)
    r2 = run_plan(db_session, plan)
    db_session.flush()
    assert r2.drafts_emitted >= 1, "Should still emit"
    assert r2.drafts_superseded == 0, "Freshly re-emitted draft should NOT be superseded"

    pending = db_session.query(Draft).filter_by(plan_id=plan.id, status="pending").all()
    assert len(pending) >= 1
    superseded = db_session.query(Draft).filter_by(plan_id=plan.id, status="superseded").all()
    assert len(superseded) == 0


def test_superseded_excluded_from_list_pending(db_session, setup):
    """list_pending should not return superseded drafts."""
    s = _make_strategy(db_session)
    plan = _make_plan(db_session, strategy_id=s.id, scope_codes=["600519"])

    # Manually insert a pending draft, then mark it superseded
    d = Draft(
        plan_id=plan.id, code="600519", side="BUY", status="superseded",
        step_kind="buy_ladder", step_index=0,
        add_pct=0.10, reason="test",
    )
    db_session.add(d)
    db_session.flush()

    pending = draft_service.list_pending(db_session)
    assert d.id not in {x.id for x in pending}
