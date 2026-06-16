"""Tests for thesis_variable_sync_service (post-T6.1 refactor).

After T6.1, templates are loaded from BusinessPattern table, not from the
module-level constant. Stocks must have ``business_pattern_id`` set to
participate in sync. Tests reflect this contract.
"""

import json
from datetime import date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.financial import FinancialStatement
from app.models.holding import Holding
from app.models.stock import Stock
from app.services import thesis_variable_sync_service as svc
from app.services.business_pattern_service import create_pattern


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _make_bank_pattern(db):
    """Create the builtin '银行' pattern with 4 lixinger-source variables."""
    return create_pattern(
        db,
        name="银行",
        first_principle_variable="股息 + 地域 + 长周期现金流/净利润匹配",
        power_tier_baseline=1,
        thesis_variables=[
            {"name": "不良贷款率", "unit": "%", "source": "lixinger"},
            {"name": "拨备覆盖率", "unit": "%", "source": "lixinger"},
            {"name": "净息差", "unit": "%", "source": "lixinger"},
            {"name": "核心一级资本充足率", "unit": "%", "source": "lixinger"},
        ],
        lixinger_industries=["银行"],
        source_ref="invest3 §11",
        is_builtin=True,
    )


def _make_chemical_pattern(db):
    """Create a pattern with only manual-source variables."""
    return create_pattern(
        db,
        name="煤化工",
        first_principle_variable="煤油价差套利",
        power_tier_baseline=2,
        thesis_variables=[
            {"name": "煤油比", "unit": "", "source": "manual"},
            {"name": "烯烃吨成本", "unit": "元/吨", "source": "manual"},
            {"name": "产能利用率", "unit": "%", "source": "manual"},
        ],
        lixinger_industries=["煤化工"],
        source_ref="invest1 第二章",
        is_builtin=True,
    )


def _make_stock(db, code="600000", industry="银行"):
    stock = Stock(code=code, name="测试银行", industry=industry)
    db.add(stock)
    db.flush()
    return stock


def _make_financial(
    db,
    stock_code,
    npl_ratio=1.5,
    provision_coverage_ratio=200.0,
    net_interest_margin=2.1,
    core_tier1_car=10.5,
):
    stmt = FinancialStatement(
        stock_code=stock_code,
        report_date=datetime(2025, 12, 31),
        report_type="annual",
        npl_ratio=npl_ratio,
        provision_coverage_ratio=provision_coverage_ratio,
        net_interest_margin=net_interest_margin,
        core_tier1_car=core_tier1_car,
    )
    db.add(stmt)
    db.flush()
    return stmt


def _make_holding(db, stock_code):
    h = Holding(
        stock_code=stock_code,
        buy_date=date(2025, 1, 1),
        buy_price=10.0,
        quantity=100,
        stop_profit_price=15.0,
    )
    db.add(h)
    db.flush()
    return h


class TestSyncStock:

    def test_sync_bank_stock(self, db):
        pattern = _make_bank_pattern(db)
        stock = _make_stock(db, industry="银行")
        stock.business_pattern_id = pattern.id
        db.flush()
        _make_financial(db, stock.code)

        result = svc.sync_stock(db, stock.code, audit=False)
        assert result["synced"] == 4
        assert "updated" in result

        variables = json.loads(stock.thesis_variables_json)
        by_name = {v["name"]: v for v in variables}
        # v2 Q1': unified schema uses `value` (not `current_value`)
        assert by_name["不良贷款率"]["value"] == 1.5
        assert by_name["拨备覆盖率"]["value"] == 200.0
        assert by_name["净息差"]["value"] == 2.1
        assert by_name["核心一级资本充足率"]["value"] == 10.5

    def test_sync_preserves_manual_vars(self, db):
        pattern = _make_chemical_pattern(db)
        stock = _make_stock(db, industry="煤化工")
        stock.business_pattern_id = pattern.id
        stock.thesis_variables_json = json.dumps(
            [{"name": "煤油比", "value": 0.5, "source": "manual", "unit": ""}]
        )
        db.flush()

        result = svc.sync_stock(db, stock.code, audit=False)
        assert result["reason"] == "all_manual"
        assert result["skipped"] == 3

    def test_no_pattern(self, db):
        """Stock without business_pattern_id is skipped with reason='no_pattern'."""
        stock = _make_stock(db, industry="银行")
        # No pattern set
        result = svc.sync_stock(db, stock.code, audit=False)
        assert result["reason"] == "no_pattern"

    def test_no_template(self, db):
        """Pattern exists but has empty thesis_variables_json."""
        from app.services.business_pattern_service import create_pattern

        pattern = create_pattern(
            db, name="空模板", thesis_variables=[], is_builtin=False
        )
        stock = _make_stock(db, industry="银行")
        stock.business_pattern_id = pattern.id
        db.flush()

        result = svc.sync_stock(db, stock.code, audit=False)
        assert result["reason"] == "no_template"

    def test_no_financials(self, db):
        pattern = _make_bank_pattern(db)
        stock = _make_stock(db, industry="银行")
        stock.business_pattern_id = pattern.id
        db.flush()

        result = svc.sync_stock(db, stock.code, audit=False)
        assert result["reason"] == "no_financials"

    def test_no_stock(self, db):
        result = svc.sync_stock(db, "999999", audit=False)
        assert result["reason"] == "no_stock"


class TestSyncAllHeld:

    def test_sync_all_held(self, db):
        pattern = _make_bank_pattern(db)
        stock = _make_stock(db, code="600000", industry="银行")
        stock.business_pattern_id = pattern.id
        db.flush()
        _make_financial(db, stock.code)
        _make_holding(db, stock.code)

        result = svc.sync_all_held(db)
        assert result["stocks"] == 1
        assert result["synced"] == 4


class TestTemplates:

    def test_get_template_for_bank_pattern(self, db):
        pattern = _make_bank_pattern(db)
        tpl = svc.get_template_for_pattern(db, pattern.id)
        assert len(tpl) == 4
        assert all(t["source"] == "lixinger" for t in tpl)

    def test_get_template_none(self, db):
        assert svc.get_template_for_pattern(db, None) == []

    def test_get_template_unknown_id(self, db):
        assert svc.get_template_for_pattern(db, 99999) == []
