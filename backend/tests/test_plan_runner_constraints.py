"""Test plan_runner S2.5 constraints — skip suspended + T+1 SELL + BUY qty."""
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.broker_fee_config import BrokerFeeConfig
from app.models.cash_balance import CashBalance
from app.models.plan import Plan
from app.models.price_kline import PriceKline
from app.models.stock import Stock
from app.models.strategy import Strategy
from app.models.valuation import ValuationSnapshot
from app.models.watchlist import WatchlistGroup, WatchlistItem
from app.services.plan_runner import run_plan
from app.services.trade_service import record_trade


# ---------------------------------------------------------------------------
# Fixtures — local in-memory SQLite (matches test_trade_service_constraints)
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session():
    """Create an in-memory SQLite session with all tables."""
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    import app.models  # noqa: F401 — register all ORM tables
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _make_strategy(db_session, **rule_kwargs) -> Strategy:
    """Create a trivial-pass strategy (single always-true condition).

    Default rule passes any stock whose dyr >= 0 (i.e. pays any dividend).
    Override ``conditions`` via kwarg to change behavior.
    """
    import json as _json
    default_rule = {
        "logic": "AND",
        "conditions": [
            {"field": "dyr", "op": ">=", "value": 0.0},
        ],
    }
    default_rule.update(rule_kwargs)
    s = Strategy(
        name="trivial-pass",
        slug="trivial-pass",
        description="",
        kind="custom",
        rule_json=_json.dumps(default_rule),
        is_builtin=False,
    )
    db_session.add(s)
    db_session.flush()
    return s


def _make_plan(
    db_session,
    *,
    strategy_id: int,
    scope_codes: list[str],
    trading_rules: dict | None = None,
) -> Plan:
    import json as _json
    plan = Plan(
        name="test-plan",
        slug="test_plan",
        description="",
        status="active",
        strategy_composition_json=_json.dumps({
            "strategy_ids": [strategy_id],
            "logic": "AND",
        }),
        scan_scope_json=_json.dumps({
            "type": "custom",
            "values": scope_codes,
        }),
        trading_rules_json=_json.dumps(trading_rules) if trading_rules else None,
        is_builtin=False,
    )
    db_session.add(plan)
    db_session.flush()
    return plan


@pytest.fixture
def setup(db_session):
    """Two stocks (one normally_listed, one suspended) + cash + fee config.

    Both stocks get a ValuationSnapshot (dyr=5%, pe_pct_10y=30%) so the
    strategy_screening pass produces a non-None context.dyr.
    """
    today = date.today()
    db_session.add(Stock(
        code="600519", name="贵州茅台", exchange="sh",
        listing_status="normally_listed", prev_close=100.0,
        industry="白酒",
    ))
    db_session.add(Stock(
        code="600002", name="暂停上市", exchange="sh",
        listing_status="ipo_suspension", prev_close=50.0,
        industry="银行",
    ))
    # Valuation snapshots (source of ctx.dyr / ctx.pe_pct_10y)
    for code in ("600519", "600002"):
        db_session.add(ValuationSnapshot(
            stock_code=code, date=today,
            dividend_yield=0.05,
            pe_percentile_10y=30.0,  # ctx.pe_pct_10y = 0.30
            pb_percentile_10y=20.0,
            pe_ttm=20.0, pb=3.0,
        ))
    # Kline for latest price proxy
    db_session.add(PriceKline(
        stock_code="600519", date=today, freq="day",
        open=99.0, high=102.0, low=98.0, close=100.0, volume=1e6,
    ))
    db_session.add(PriceKline(
        stock_code="600002", date=today, freq="day",
        open=49.5, high=51.0, low=49.0, close=50.0, volume=1e5,
    ))
    db_session.add(CashBalance(id=1, balance=1000000.0))
    db_session.add(BrokerFeeConfig(
        broker_name="default", commission_rate=0.00025, commission_min=5.0,
        stamp_duty_rate=0.0005, transfer_fee_rate=0.00001,
        effective_from=date(2023, 10, 23), is_active=True,
    ))
    # S3.5 — seed data_freshness so plan_runner.run_plan's freshness gate
    # does not reject the run. stocks + valuation both gate, both fresh.
    from app.services.data_freshness_service import (
        record_sync_success as _rss,
    )
    _rss(db_session, "stocks", record_count=2)
    _rss(db_session, "valuation", record_count=2)
    db_session.flush()


# ---------------------------------------------------------------------------
# Suspended filtering
# ---------------------------------------------------------------------------


def test_suspended_stock_skipped_from_scan(db_session, setup):
    """600002 (ipo_suspension) should never enter the candidate pool."""
    s = _make_strategy(db_session)
    plan = _make_plan(db_session, strategy_id=s.id, scope_codes=["600519", "600002"])
    # No trading rules — just screening.

    result = run_plan(db_session, plan)
    db_session.flush()

    from app.models.candidate import Candidate
    active = db_session.query(Candidate).filter_by(
        plan_id=plan.id, status="active",
    ).all()
    codes = {c.stock_code for c in active}

    assert "600519" in codes, "正常股 600519 应该入选"
    assert "600002" not in codes, "停牌股 600002 应被过滤掉"
    # 600002 should not even count as scanned (filtered before evaluation)
    # but we accept either: it counts as scanned, just not as passed
    assert result.passed >= 1


def test_suspended_stock_no_draft(db_session, setup):
    """停牌股即便在 watchlist + 触发买阶梯,也不应该产生 Draft."""
    s = _make_strategy(db_session)
    rules = {
        "buy_ladder": [
            {"trigger": {"kind": "dyr_ge", "value": 0.04}, "add_pct": 0.10},
        ],
        "sell_ladder": [],
        "invalidation": [],
        "cooldown_days": 0,
    }
    plan = _make_plan(
        db_session, strategy_id=s.id,
        scope_codes=["600519", "600002"],
        trading_rules=rules,
    )
    # Both in watchlist
    wg = WatchlistGroup(name="g1")
    db_session.add(wg); db_session.flush()
    db_session.add(WatchlistItem(group_id=wg.id, stock_code="600519"))
    db_session.add(WatchlistItem(group_id=wg.id, stock_code="600002"))
    db_session.flush()

    run_plan(db_session, plan)
    db_session.flush()

    from app.models.draft import Draft
    drafts = db_session.query(Draft).filter_by(plan_id=plan.id).all()
    codes = {d.code for d in drafts}
    assert "600002" not in codes, "停牌股不应该有 Draft"
    assert "600519" in codes, "正常股应该有 BUY draft"


# ---------------------------------------------------------------------------
# SELL T+1 check
# ---------------------------------------------------------------------------


def test_sell_draft_skipped_when_no_position(db_session, setup):
    """持仓为 0 时,SELL 触发条件满足也不应该生成 SELL draft."""
    s = _make_strategy(db_session)
    # SELL on dyr <= 0.06 — 600519 dyr=0.05 will trigger
    rules = {
        "buy_ladder": [],
        "sell_ladder": [
            {"trigger": {"kind": "dyr_le", "value": 0.06},
             "reduce_pct_of_position": 0.50},
        ],
        "invalidation": [],
        "cooldown_days": 0,
    }
    plan = _make_plan(
        db_session, strategy_id=s.id, scope_codes=["600519"],
        trading_rules=rules,
    )
    wg = WatchlistGroup(name="g1")
    db_session.add(wg); db_session.flush()
    db_session.add(WatchlistItem(group_id=wg.id, stock_code="600519"))
    db_session.flush()

    # No prior BUY trade — available = 0
    run_plan(db_session, plan)
    db_session.flush()

    from app.models.draft import Draft
    sells = db_session.query(Draft).filter_by(
        plan_id=plan.id, side="SELL",
    ).all()
    assert len(sells) == 0, "持仓 0 不应生成 SELL draft"


def test_sell_draft_emitted_when_position_settled(db_session, setup):
    """昨日买入今日可卖 — available > 0,SELL draft 应生成."""
    s = _make_strategy(db_session)
    rules = {
        "buy_ladder": [],
        "sell_ladder": [
            {"trigger": {"kind": "dyr_le", "value": 0.06},
             "reduce_pct_of_position": 0.50},
        ],
        "invalidation": [],
        "cooldown_days": 0,
    }
    plan = _make_plan(
        db_session, strategy_id=s.id, scope_codes=["600519"],
        trading_rules=rules,
    )
    wg = WatchlistGroup(name="g1")
    db_session.add(wg); db_session.flush()
    db_session.add(WatchlistItem(group_id=wg.id, stock_code="600519"))
    db_session.flush()

    # Yesterday BUY → settled today
    yesterday = datetime.now() - timedelta(days=2)
    record_trade(
        db_session, stock_code="600519", side="BUY",
        price=100.0, quantity=100,
        filled_at=yesterday, source="manual",
    )
    db_session.flush()

    run_plan(db_session, plan)
    db_session.flush()

    from app.models.draft import Draft
    sells = db_session.query(Draft).filter_by(
        plan_id=plan.id, side="SELL",
    ).all()
    assert len(sells) == 1, "available > 0 时应生成 SELL draft"


# ---------------------------------------------------------------------------
# BUY suggested_quantity
# ---------------------------------------------------------------------------


def test_buy_draft_populates_suggested_quantity(db_session, setup):
    """BUY draft 应填 suggested_quantity(100 的倍数)."""
    s = _make_strategy(db_session)
    rules = {
        "buy_ladder": [
            {"trigger": {"kind": "dyr_ge", "value": 0.04}, "add_pct": 0.10},
        ],
        "sell_ladder": [],
        "invalidation": [],
        "cooldown_days": 0,
    }
    plan = _make_plan(
        db_session, strategy_id=s.id, scope_codes=["600519"],
        trading_rules=rules,
    )
    wg = WatchlistGroup(name="g1")
    db_session.add(wg); db_session.flush()
    db_session.add(WatchlistItem(group_id=wg.id, stock_code="600519"))
    db_session.flush()

    run_plan(db_session, plan)
    db_session.flush()

    from app.models.draft import Draft
    buys = db_session.query(Draft).filter_by(
        plan_id=plan.id, side="BUY",
    ).all()
    assert len(buys) == 1
    qty = buys[0].suggested_quantity
    assert qty is not None, "BUY draft 应有 suggested_quantity"
    assert qty > 0, f"suggested_quantity 应 > 0, got {qty}"
    assert qty % 100 == 0, f"suggested_quantity 应是 100 的倍数, got {qty}"


def test_buy_suggested_quantity_reasonable_value(db_session, setup):
    """NAV=1M,target=10%,prev_close=100 → 10% × 1M / 100 = 1000 shares."""
    s = _make_strategy(db_session)
    rules = {
        "buy_ladder": [
            {"trigger": {"kind": "dyr_ge", "value": 0.04}, "add_pct": 0.10},
        ],
        "sell_ladder": [],
        "invalidation": [],
        "cooldown_days": 0,
    }
    plan = _make_plan(
        db_session, strategy_id=s.id, scope_codes=["600519"],
        trading_rules=rules,
    )
    wg = WatchlistGroup(name="g1")
    db_session.add(wg); db_session.flush()
    db_session.add(WatchlistItem(group_id=wg.id, stock_code="600519"))
    db_session.flush()

    run_plan(db_session, plan)
    db_session.flush()

    from app.models.draft import Draft
    buy = db_session.query(Draft).filter_by(
        plan_id=plan.id, side="BUY",
    ).one()
    # 1M × 10% = 100k budget. 100k / 100/share = 1000 shares.
    # Fees < 5% of budget, so should still get 1000.
    assert buy.suggested_quantity == 1000, (
        f"expected 1000 shares for 1M × 10% / 100 = 1000, got {buy.suggested_quantity}"
    )


# ---------------------------------------------------------------------------
# SELL draft suggested_quantity is None
# ---------------------------------------------------------------------------


def test_sell_draft_suggested_quantity_is_none(db_session, setup):
    """SELL draft 不应填 suggested_quantity(只有 BUY 才有)."""
    s = _make_strategy(db_session)
    rules = {
        "buy_ladder": [],
        "sell_ladder": [
            {"trigger": {"kind": "dyr_le", "value": 0.06},
             "reduce_pct_of_position": 0.50},
        ],
        "invalidation": [],
        "cooldown_days": 0,
    }
    plan = _make_plan(
        db_session, strategy_id=s.id, scope_codes=["600519"],
        trading_rules=rules,
    )
    wg = WatchlistGroup(name="g1")
    db_session.add(wg); db_session.flush()
    db_session.add(WatchlistItem(group_id=wg.id, stock_code="600519"))
    db_session.flush()

    yesterday = datetime.now() - timedelta(days=2)
    record_trade(
        db_session, stock_code="600519", side="BUY",
        price=100.0, quantity=100,
        filled_at=yesterday, source="manual",
    )
    db_session.flush()

    run_plan(db_session, plan)
    db_session.flush()

    from app.models.draft import Draft
    sell = db_session.query(Draft).filter_by(
        plan_id=plan.id, side="SELL",
    ).one()
    assert sell.suggested_quantity is None, "SELL draft 的 suggested_quantity 应为 None"
