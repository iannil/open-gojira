"""Test publish_date_resolver + point_in_time_context_service."""
from datetime import date
import pytest

from app.models.historical_kline import HistoricalKline
from app.models.historical_valuation import HistoricalValuation
from app.models.historical_financial import HistoricalFinancial
from app.models.stock import Stock
from app.services.point_in_time_context_service import (
    build_context_at, get_kline_at, get_valuation_at,
    get_latest_financial_as_of, get_publish_date,
)


@pytest.fixture
def setup(db_session):
    db_session.add(Stock(code="600519", name="贵州茅台", exchange="sh"))
    db_session.flush()
    # K 线
    db_session.add(HistoricalKline(
        stock_code="600519", date=date(2025, 4, 14),
        open=1, high=1, low=1, close=100, volume=1, amount=1,
    ))
    db_session.add(HistoricalKline(
        stock_code="600519", date=date(2025, 4, 15),
        open=1, high=1, low=1, close=101, volume=1, amount=1,
    ))
    db_session.add(HistoricalKline(
        stock_code="600519", date=date(2025, 4, 16),
        open=1, high=1, low=1, close=102, volume=1, amount=1,
    ))
    # 估值
    db_session.add(HistoricalValuation(
        stock_code="600519", date=date(2025, 4, 15),
        pe_ttm=30, pb=10, sp=101,
    ))
    # 财报:2024 年报 reportDate=2025-04-30(还在未来)
    db_session.add(HistoricalFinancial(
        stock_code="600519", period=date(2024, 12, 31),
        report_date=date(2025, 4, 30),
        report_type="annual_report",
        revenue=150000000000, net_profit=85000000000,
    ))
    # 2024 三季报 reportDate=2024-10-26(已披露)
    db_session.add(HistoricalFinancial(
        stock_code="600519", period=date(2024, 9, 30),
        report_date=date(2024, 10, 26),
        report_type="third_quarterly_report",
        revenue=120000000000, net_profit=60000000000,
    ))
    db_session.flush()


# --- get_publish_date ---

def test_get_publish_date_reads_field():
    record = {"reportDate": "2025-04-30", "date": "2024-12-31"}
    pd = get_publish_date(record)
    assert pd == date(2025, 4, 30)


def test_get_publish_date_fallback_to_csrc_ceiling():
    """If reportDate missing, use CSRC ceiling by report_type."""
    record = {"date": "2024-12-31", "reportType": "annual_report"}
    pd = get_publish_date(record)
    # annual report CSRC max = 120 days
    assert pd == date(2025, 4, 30)  # 2024-12-31 + 120 days


def test_get_publish_date_fallback_unknown_type():
    """Unknown type uses conservative 120 day default."""
    record = {"date": "2024-12-31"}
    pd = get_publish_date(record)
    assert pd == date(2025, 4, 30)


def test_get_publish_date_invalid_returns_none():
    assert get_publish_date({}) is None


# --- get_kline_at ---

def test_get_kline_at_exact_day(db_session, setup):
    k = get_kline_at(db_session, "600519", date(2025, 4, 15))
    assert k is not None
    assert k.close == 101


def test_get_kline_at_no_data(db_session, setup):
    k = get_kline_at(db_session, "600519", date(2025, 5, 1))
    assert k is None


# --- get_valuation_at ---

def test_get_valuation_at(db_session, setup):
    v = get_valuation_at(db_session, "600519", date(2025, 4, 15))
    assert v is not None
    assert v.pe_ttm == 30
    assert v.sp == 101


# --- get_latest_financial_as_of ---

def test_get_latest_financial_excludes_future_reports(db_session, setup):
    """On 2025-04-15, the 2024 annual report (reportDate=2025-04-30)
    is NOT yet published — only Q3 should be returned."""
    fin = get_latest_financial_as_of(db_session, "600519", date(2025, 4, 15))
    assert fin is not None
    assert fin.period == date(2024, 9, 30)  # Q3 not annual
    assert fin.report_date == date(2024, 10, 26)


def test_get_latest_financial_includes_after_publish(db_session, setup):
    """On 2025-05-15, annual report is published (reportDate=2025-04-30)."""
    fin = get_latest_financial_as_of(db_session, "600519", date(2025, 5, 15))
    assert fin is not None
    assert fin.period == date(2024, 12, 31)


def test_get_latest_financial_no_data(db_session, setup):
    """Stock with no financials returns None."""
    db_session.add(Stock(code="600000", name="Test", exchange="sh"))
    db_session.flush()
    fin = get_latest_financial_as_of(db_session, "600000", date(2025, 1, 1))
    assert fin is None


# --- build_context_at (composite) ---

def test_build_context_at_assembles_all_data(db_session, setup):
    ctx = build_context_at(db_session, "600519", date(2025, 4, 15))
    assert ctx.stock_code == "600519"
    assert ctx.day == date(2025, 4, 15)
    assert ctx.kline is not None
    assert ctx.kline.close == 101
    assert ctx.valuation is not None
    assert ctx.valuation.pe_ttm == 30
    assert ctx.financial is not None
    assert ctx.financial.period == date(2024, 9, 30)  # point-in-time correctness


def test_build_context_at_missing_kline(db_session, setup):
    """If kline missing for the day, context still assembles other data."""
    ctx = build_context_at(db_session, "600519", date(2025, 5, 1))
    assert ctx.kline is None  # no kline on 2025-05-01
    # financial still available
    assert ctx.financial is not None
