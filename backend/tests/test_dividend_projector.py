"""Tests for dividend_projector_service — 股息收入预测."""

import pytest
from datetime import date

from tests.conftest import TestSessionLocal
from app.models.cashflow_goal import CashflowGoal
from app.models.dividend import DividendRecord
from app.models.holding import Holding
from app.models.stock import Stock
from app.models.valuation import ValuationSnapshot
from app.services.dividend_projector_service import project


@pytest.fixture
def db():
    session = TestSessionLocal()
    yield session
    session.close()


class TestDividendProjectionEmpty:
    def test_no_holdings_returns_zero(self, db):
        result = project(db)
        assert result.next_12m_expected == 0.0
        assert result.by_holding == []
        assert result.trailing_12m_actual == 0.0


class TestDividendProjection:
    def test_projects_from_historical_dividends(self, db):
        db.add(Stock(code="601398", name="工商银行", industry="银行"))
        db.add(Holding(stock_code="601398", buy_date=date(2025, 1, 1),
                       buy_price=5.0, quantity=2000, stop_profit_price=999.0))
        db.add(DividendRecord(stock_code="601398", ex_date=date(2025, 6, 15),
                              amount_per_share=0.30, quantity_held=2000, total_received=600.0))
        db.add(DividendRecord(stock_code="601398", ex_date=date(2024, 6, 15),
                              amount_per_share=0.29, quantity_held=2000, total_received=580.0))
        db.add(ValuationSnapshot(stock_code="601398", date=date(2026, 6, 6),
                                 dividend_yield=0.06))
        db.commit()

        result = project(db)
        assert len(result.by_holding) == 1
        h = result.by_holding[0]
        assert h.code == "601398"
        assert h.expected_per_share > 0
        assert h.expected_total == h.expected_per_share * 2000
        assert h.expected_ex_month == 6

    def test_projects_from_yield_when_no_history(self, db):
        db.add(Stock(code="600028", name="中国石化", industry="石油"))
        db.add(Holding(stock_code="600028", buy_date=date(2025, 1, 1),
                       buy_price=6.0, quantity=1000, stop_profit_price=999.0))
        db.add(ValuationSnapshot(stock_code="600028", date=date(2026, 6, 6),
                                 dividend_yield=0.08))
        db.commit()

        result = project(db)
        assert len(result.by_holding) == 1
        h = result.by_holding[0]
        assert h.code == "600028"
        # Expected = dyr * buy_price * quantity = 0.08 * 6.0 * 1000 = 480
        assert h.expected_total > 0

    def test_with_cashflow_goal(self, db):
        db.add(Stock(code="601398", name="工商银行", industry="银行"))
        db.add(Holding(stock_code="601398", buy_date=date(2025, 1, 1),
                       buy_price=5.0, quantity=2000, stop_profit_price=999.0))
        db.add(DividendRecord(stock_code="601398", ex_date=date(2025, 6, 15),
                              amount_per_share=0.30, quantity_held=2000, total_received=600.0))
        db.add(ValuationSnapshot(stock_code="601398", date=date(2026, 6, 6),
                                 dividend_yield=0.06))
        db.add(CashflowGoal(
            id=1,
            annual_expense=50000,
            goal_multiple=20,
        ))
        db.commit()

        result = project(db)
        assert result.annual_passive_target == 1000000.0  # 50000 * 20
        assert result.dividend_gap is not None
        assert result.dividend_coverage is not None
        assert result.dividend_coverage < 1.0  # 600 < 100000


class TestTrailing12m:
    def test_trailing_12m_actual(self, db):
        db.add(DividendRecord(stock_code="X", ex_date=date(2026, 1, 15),
                              amount_per_share=0.10, quantity_held=100, total_received=10.0))
        db.add(DividendRecord(stock_code="X", ex_date=date(2025, 1, 15),
                              amount_per_share=0.10, quantity_held=100, total_received=10.0))
        db.commit()

        result = project(db)
        assert result.trailing_12m_actual == 10.0
