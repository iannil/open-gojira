"""D3 (2026-06-17 invest-alignment audit): plan_runner 财报红旗过滤集成测试.

invest1 §三 + invest2 §10: 候选股触发任何红旗 → 从 plan 候选池剔除。
"""
from datetime import date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.broker_fee_config import BrokerFeeConfig
from app.models.cash_balance import CashBalance
from app.models.financial import FinancialStatement
from app.models.plan import Plan
from app.models.stock import Stock
from app.models.strategy import Strategy
from app.models.valuation import ValuationSnapshot
from app.services.plan_runner import run_plan


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _setup(db, code: str, *, trigger_goodwill_red_flag: bool = False):
    """Set up a single stock with valuation + optional goodwill red flag."""
    today = date.today()
    db.add(Stock(
        code=code, name=f"测试 {code}", exchange="sh",
        listing_status="normally_listed", prev_close=100.0,
        industry="白酒",
        in_circle=True,
    ))
    db.add(ValuationSnapshot(
        stock_code=code, date=today,
        dividend_yield=0.05,
        pe_percentile_10y=30.0,
        pb_percentile_10y=20.0,
        pe_ttm=20.0, pb=3.0,
    ))
    if trigger_goodwill_red_flag:
        # 触发 goodwill_to_equity_gt_50 红旗
        db.add(FinancialStatement(
            stock_code=code,
            report_date=datetime(2025, 12, 31),
            report_type="annual",
            revenue=1e9, net_profit=1e8,
            shareholders_equity=1e9,
            goodwill=6e8,  # 60% > 50% threshold
            operating_cash_flow=1.2e8,  # 健康 OCF
        ))
    else:
        db.add(FinancialStatement(
            stock_code=code,
            report_date=datetime(2025, 12, 31),
            report_type="annual",
            revenue=1e9, net_profit=1e8,
            shareholders_equity=1e9,
            goodwill=0,
            operating_cash_flow=1.2e8,
        ))
    db.add(CashBalance(id=1, balance=1000000.0))
    db.add(BrokerFeeConfig(
        broker_name="default", commission_rate=0.00025, commission_min=5.0,
        stamp_duty_rate=0.0005, transfer_fee_rate=0.00001,
        effective_from=date(2023, 10, 23), is_active=True,
    ))
    from app.services.data_freshness_service import record_sync_success
    record_sync_success(db, "stocks", record_count=1)
    record_sync_success(db, "valuation", record_count=1)
    db.flush()


def _make_strategy(db) -> Strategy:
    import json
    s = Strategy(
        name="trivial-pass", slug="trivial-pass", description="",
        kind="custom",
        rule_json=json.dumps({
            "logic": "AND",
            "conditions": [{"field": "dyr", "op": ">=", "value": 0.0}],
        }),
        is_builtin=False,
    )
    db.add(s)
    db.flush()
    return s


def _make_plan(db, strategy_id: int, codes: list[str]) -> Plan:
    import json
    p = Plan(
        name="test-plan", slug="test_plan", description="",
        status="active",
        strategy_composition_json=json.dumps({
            "strategy_ids": [strategy_id], "logic": "AND",
        }),
        scan_scope_json=json.dumps({"type": "custom", "values": codes}),
        is_builtin=False,
    )
    db.add(p)
    db.flush()
    return p


class TestRedFlagFilter:
    """plan_runner 应在候选股触发财报红旗时将其过滤掉。"""

    def test_clean_stock_becomes_candidate(self, db_session):
        """No red flag → stock should enter candidate pool."""
        _setup(db_session, "600519", trigger_goodwill_red_flag=False)
        s = _make_strategy(db_session)
        plan = _make_plan(db_session, s.id, ["600519"])

        result = run_plan(db_session, plan)
        assert result.filtered_red_flags == 0
        assert result.passed >= 1

    def test_red_flag_stock_filtered(self, db_session):
        """Trigger goodwill red flag → stock should be filtered, not enter pool."""
        _setup(db_session, "600519", trigger_goodwill_red_flag=True)
        s = _make_strategy(db_session)
        plan = _make_plan(db_session, s.id, ["600519"])

        result = run_plan(db_session, plan)
        assert result.filtered_red_flags >= 1
        assert result.passed == 0

        from app.models.candidate import Candidate
        active = db_session.query(Candidate).filter_by(
            plan_id=plan.id, status="active",
        ).all()
        assert len(active) == 0
