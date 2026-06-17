"""Tests for red_flag_detector_service — invest1 §三 + invest2 §10 财报避坑."""
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.financial import FinancialStatement
from app.models.stock import Stock
from app.services.red_flag_detector_service import (
    RedFlagReport,
    detect_financial_red_flags,
    detect_with_dividend_sustainability,
    _GOODWILL_EQUITY_THRESHOLD,
    _OCF_NI_LOW,
    _LOW_DIV_SUST,
)


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


def _add_stock(db, code="600519"):
    db.add(Stock(code=code, name="测试股", industry="白酒"))
    db.commit()


def _add_stmt(
    db, code, report_date, *,
    revenue=1e9, revenue_growth=0.10, net_profit=1e8,
    shareholders_equity=1e9, goodwill=0.0,
    operating_cash_flow=None,  # default = net_profit (健康)
    accounts_receivable=None, inventory=None,
    inventory_turnover_ratio=None, non_recurring_profit_ratio=None,
    net_margin=0.10,
):
    """Add one annual FinancialStatement row."""
    if operating_cash_flow is None:
        operating_cash_flow = net_profit * 1.2  # 健康 default
    db.add(FinancialStatement(
        stock_code=code,
        report_date=datetime.strptime(report_date, "%Y-%m-%d"),
        report_type="annual",
        revenue=revenue,
        revenue_growth=revenue_growth,
        net_profit=net_profit,
        shareholders_equity=shareholders_equity,
        goodwill=goodwill,
        operating_cash_flow=operating_cash_flow,
        accounts_receivable=accounts_receivable,
        inventory=inventory,
        inventory_turnover_ratio=inventory_turnover_ratio,
        non_recurring_profit_ratio=non_recurring_profit_ratio,
        net_margin=net_margin,
    ))
    db.commit()


# ---------------------------------------------------------------------------
# Empty cases
# ---------------------------------------------------------------------------


class TestEmptyCases:
    def test_no_data_returns_empty_report(self, db_session):
        _add_stock(db_session, "600519")
        # No FinancialStatement rows
        report = detect_financial_red_flags(db_session, "600519")
        assert report.count == 0
        assert report.kinds == []


# ---------------------------------------------------------------------------
# Goodwill flag
# ---------------------------------------------------------------------------


class TestGoodwillFlag:
    def test_goodwill_over_50pct_triggers(self, db_session):
        _add_stock(db_session, "600519")
        _add_stmt(db_session, "600519", "2025-12-31",
                  shareholders_equity=1e9, goodwill=6e8)  # 60%
        report = detect_financial_red_flags(db_session, "600519")
        assert "goodwill_to_equity_gt_50" in report.kinds

    def test_goodwill_under_50pct_no_flag(self, db_session):
        _add_stock(db_session, "600519")
        _add_stmt(db_session, "600519", "2025-12-31",
                  shareholders_equity=1e9, goodwill=4e8)  # 40%
        report = detect_financial_red_flags(db_session, "600519")
        assert "goodwill_to_equity_gt_50" not in report.kinds

    def test_no_goodwill_field_skips_check(self, db_session):
        _add_stock(db_session, "600519")
        _add_stmt(db_session, "600519", "2025-12-31",
                  shareholders_equity=1e9, goodwill=0)
        report = detect_financial_red_flags(db_session, "600519")
        assert "goodwill_to_equity_gt_50" not in report.kinds


# ---------------------------------------------------------------------------
# OCF/NI flag
# ---------------------------------------------------------------------------


class TestOcfNiFlag:
    def test_low_ocf_2y_triggers(self, db_session):
        _add_stock(db_session, "600519")
        # 2 期都 OCF < 0.5x net_profit
        _add_stmt(db_session, "600519", "2025-12-31",
                  net_profit=1e8, operating_cash_flow=2e7)  # 0.2
        _add_stmt(db_session, "600519", "2024-12-31",
                  net_profit=1e8, operating_cash_flow=3e7)  # 0.3
        report = detect_financial_red_flags(db_session, "600519")
        assert "ocf_to_ni_lt_half_2y" in report.kinds

    def test_one_year_low_no_flag(self, db_session):
        _add_stock(db_session, "600519")
        _add_stmt(db_session, "600519", "2025-12-31",
                  net_profit=1e8, operating_cash_flow=2e7)  # 0.2 low
        _add_stmt(db_session, "600519", "2024-12-31",
                  net_profit=1e8, operating_cash_flow=1.2e8)  # 1.2 healthy
        report = detect_financial_red_flags(db_session, "600519")
        assert "ocf_to_ni_lt_half_2y" not in report.kinds

    def test_only_one_year_data_no_flag(self, db_session):
        _add_stock(db_session, "600519")
        _add_stmt(db_session, "600519", "2025-12-31",
                  net_profit=1e8, operating_cash_flow=2e7)
        report = detect_financial_red_flags(db_session, "600519")
        assert "ocf_to_ni_lt_half_2y" not in report.kinds


# ---------------------------------------------------------------------------
# Dividend sustainability integration
# ---------------------------------------------------------------------------


class TestDividendSustainabilityFlag:
    def test_low_score_triggers(self, db_session):
        _add_stock(db_session, "600519")
        _add_stmt(db_session, "600519", "2025-12-31")
        report = detect_with_dividend_sustainability(
            db_session, "600519", div_sust_score=25,  # < 30
        )
        assert "low_dividend_sustainability" in report.kinds

    def test_high_score_no_flag(self, db_session):
        _add_stock(db_session, "600519")
        _add_stmt(db_session, "600519", "2025-12-31")
        report = detect_with_dividend_sustainability(
            db_session, "600519", div_sust_score=70,
        )
        assert "low_dividend_sustainability" not in report.kinds

    def test_none_score_no_flag(self, db_session):
        _add_stock(db_session, "600519")
        _add_stmt(db_session, "600519", "2025-12-31")
        report = detect_with_dividend_sustainability(
            db_session, "600519", div_sust_score=None,
        )
        assert "low_dividend_sustainability" not in report.kinds


# ---------------------------------------------------------------------------
# AR growth flag
# ---------------------------------------------------------------------------


class TestArGrowthFlag:
    def test_ar_growth_2x_revenue_triggers(self, db_session):
        _add_stock(db_session, "600519")
        # latest: AR 1.5e8 (50% 增长), revenue 1e9 (5% 增长)
        _add_stmt(db_session, "600519", "2025-12-31",
                  revenue=1e9, accounts_receivable=1.5e8)
        # prev: AR 1e8, revenue 9.5e8
        _add_stmt(db_session, "600519", "2024-12-31",
                  revenue=9.5e8, accounts_receivable=1e8)
        report = detect_financial_red_flags(db_session, "600519")
        assert "ar_growth_gt_revenue" in report.kinds

    def test_ar_growth_aligned_with_revenue_no_flag(self, db_session):
        _add_stock(db_session, "600519")
        _add_stmt(db_session, "600519", "2025-12-31",
                  revenue=1.2e9, accounts_receivable=1.2e8)  # +20%
        _add_stmt(db_session, "600519", "2024-12-31",
                  revenue=1e9, accounts_receivable=1e8)
        report = detect_financial_red_flags(db_session, "600519")
        assert "ar_growth_gt_revenue" not in report.kinds


# ---------------------------------------------------------------------------
# Inventory turnover drop flag
# ---------------------------------------------------------------------------


class TestInventoryTurnoverFlag:
    def test_drop_over_30pct_triggers(self, db_session):
        _add_stock(db_session, "600519")
        _add_stmt(db_session, "600519", "2025-12-31",
                  inventory_turnover_ratio=3.0)
        _add_stmt(db_session, "600519", "2024-12-31",
                  inventory_turnover_ratio=5.0)  # drop 40%
        report = detect_financial_red_flags(db_session, "600519")
        assert "inventory_turnover_drop" in report.kinds

    def test_minor_drop_no_flag(self, db_session):
        _add_stock(db_session, "600519")
        _add_stmt(db_session, "600519", "2025-12-31",
                  inventory_turnover_ratio=4.5)
        _add_stmt(db_session, "600519", "2024-12-31",
                  inventory_turnover_ratio=5.0)  # drop 10%
        report = detect_financial_red_flags(db_session, "600519")
        assert "inventory_turnover_drop" not in report.kinds


# ---------------------------------------------------------------------------
# Non-recurring dominant flag
# ---------------------------------------------------------------------------


class TestNonRecurringFlag:
    def test_dominant_non_recurring_triggers(self, db_session):
        _add_stock(db_session, "600519")
        # net_margin=10%, non_recurring=4% → 60% non-recurring share
        _add_stmt(db_session, "600519", "2025-12-31",
                  net_margin=0.10, non_recurring_profit_ratio=0.04)
        report = detect_financial_red_flags(db_session, "600519")
        assert "non_recurring_dominant" in report.kinds

    def test_healthy_main_business_no_flag(self, db_session):
        _add_stock(db_session, "600519")
        # net_margin=10%, non_recurring=9% → 10% non-recurring share
        _add_stmt(db_session, "600519", "2025-12-31",
                  net_margin=0.10, non_recurring_profit_ratio=0.09)
        report = detect_financial_red_flags(db_session, "600519")
        assert "non_recurring_dominant" not in report.kinds


# ---------------------------------------------------------------------------
# Report aggregate
# ---------------------------------------------------------------------------


class TestReportAggregate:
    def test_count_and_kinds(self, db_session):
        _add_stock(db_session, "600519")
        # 触发 goodwill + ar_growth + inventory_drop 三个红旗
        _add_stmt(db_session, "600519", "2025-12-31",
                  shareholders_equity=1e9, goodwill=6e8,  # goodwill 60%
                  revenue=1e9, accounts_receivable=1.5e8,
                  inventory_turnover_ratio=3.0)
        _add_stmt(db_session, "600519", "2024-12-31",
                  revenue=9.5e8, accounts_receivable=1e8,
                  inventory_turnover_ratio=5.0)
        report = detect_financial_red_flags(db_session, "600519")
        assert report.count >= 3
        assert "goodwill_to_equity_gt_50" in report.kinds

    def test_to_dict_serializable(self, db_session):
        _add_stock(db_session, "600519")
        _add_stmt(db_session, "600519", "2025-12-31",
                  shareholders_equity=1e9, goodwill=6e8)
        report = detect_financial_red_flags(db_session, "600519")
        d = report.to_dict()
        assert d["stock_code"] == "600519"
        assert d["count"] == report.count
        assert isinstance(d["kinds"], list)
        assert isinstance(d["details"], list)
