"""Tests for thesis_variable_sync_service."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.financial import FinancialStatement
from app.models.holding import Holding
from app.models.stock import Stock
from app.services import thesis_variable_sync_service as svc


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _make_stock(db, code="600000", industry="银行"):
    stock = Stock(code=code, name="测试银行", industry=industry)
    db.add(stock)
    db.flush()
    return stock


def _make_financial(db, stock_code, npl_ratio=1.5, provision_coverage_ratio=200.0,
                    net_interest_margin=2.1, core_tier1_car=10.5):
    from datetime import datetime
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
    from datetime import date
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
        stock = _make_stock(db, industry="银行")
        _make_financial(db, stock.code)

        result = svc.sync_stock(db, stock.code, audit=False)
        assert result["synced"] == 4
        assert "updated" in result

        import json
        variables = json.loads(stock.thesis_variables_json)
        by_name = {v["name"]: v for v in variables}
        assert by_name["不良贷款率"]["current_value"] == 1.5
        assert by_name["拨备覆盖率"]["current_value"] == 200.0
        assert by_name["净息差"]["current_value"] == 2.1
        assert by_name["核心一级资本充足率"]["current_value"] == 10.5

    def test_sync_preserves_manual_vars(self, db):
        import json
        stock = _make_stock(db, industry="煤化工")
        stock.thesis_variables_json = json.dumps([
            {"name": "煤油比", "current_value": 0.5, "source": "manual", "unit": ""}
        ])
        db.flush()

        result = svc.sync_stock(db, stock.code, audit=False)
        assert result["reason"] == "all_manual"
        assert result["skipped"] == 3

    def test_no_template(self, db):
        stock = _make_stock(db, industry="未知行业")
        result = svc.sync_stock(db, stock.code, audit=False)
        assert result["reason"] == "no_template"

    def test_no_financials(self, db):
        stock = _make_stock(db, industry="银行")
        result = svc.sync_stock(db, stock.code, audit=False)
        assert result["reason"] == "no_financials"

    def test_no_stock(self, db):
        result = svc.sync_stock(db, "999999", audit=False)
        assert result["reason"] == "no_stock_or_industry"


class TestSyncAllHeld:

    def test_sync_all_held(self, db):
        stock = _make_stock(db, code="600000", industry="银行")
        _make_financial(db, stock.code)
        _make_holding(db, stock.code)

        result = svc.sync_all_held(db)
        assert result["stocks"] == 1
        assert result["synced"] == 4


class TestTemplates:

    def test_get_template_for_industry(self):
        tpl = svc.get_template_for_industry("银行")
        assert len(tpl) == 4
        assert all(t["source"] == "lixinger" for t in tpl)

    def test_get_template_none(self):
        assert svc.get_template_for_industry(None) == []

    def test_get_template_unknown(self):
        assert svc.get_template_for_industry("未知行业") == []
