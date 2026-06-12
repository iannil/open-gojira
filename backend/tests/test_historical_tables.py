"""Test historical_valuations / historical_klines / historical_financials tables."""
from datetime import date

import pytest

from app.models.historical_financial import HistoricalFinancial
from app.models.historical_kline import HistoricalKline
from app.models.historical_valuation import HistoricalValuation


def test_historical_valuation_create(db_session):
    v = HistoricalValuation(
        stock_code="600519",
        date=date(2026, 6, 12),
        pe_ttm=30.5,
        pb=10.2,
        ps_ttm=15.0,
        dyr=0.025,
        sp=1680.0,
        mc=2100000000000,
    )
    db_session.add(v)
    db_session.commit()
    assert v.id is not None


def test_historical_valuation_unique(db_session):
    """Same stock_code + date must be unique."""
    db_session.add(
        HistoricalValuation(
            stock_code="600519",
            date=date(2026, 6, 12),
            sp=1680.0,
        )
    )
    db_session.commit()
    db_session.add(
        HistoricalValuation(
            stock_code="600519",
            date=date(2026, 6, 12),
            sp=1700.0,
        )
    )
    with pytest.raises(Exception):  # IntegrityError
        db_session.commit()


def test_historical_kline_create(db_session):
    k = HistoricalKline(
        stock_code="600519",
        date=date(2026, 6, 12),
        open=1675.0,
        high=1690.0,
        low=1670.0,
        close=1685.0,
        volume=12345678,
        amount=20800000000,
    )
    db_session.add(k)
    db_session.commit()
    assert k.id is not None


def test_historical_kline_unique(db_session):
    db_session.add(
        HistoricalKline(
            stock_code="600519",
            date=date(2026, 6, 12),
            open=1,
            high=1,
            low=1,
            close=1,
            volume=1,
            amount=1,
        )
    )
    db_session.commit()
    db_session.add(
        HistoricalKline(
            stock_code="600519",
            date=date(2026, 6, 12),
            open=2,
            high=2,
            low=2,
            close=2,
            volume=2,
            amount=2,
        )
    )
    with pytest.raises(Exception):
        db_session.commit()


def test_historical_financial_create(db_session):
    f = HistoricalFinancial(
        stock_code="600519",
        period=date(2024, 12, 31),  # 财报期
        report_date=date(2025, 4, 3),  # 实际披露日 (S0.2 验证的字段)
        report_type="annual_report",
        revenue=150000000000,
        net_profit=85000000000,
        total_assets=500000000000,
        total_equity=250000000000,
        operating_cash_flow=90000000000,
        roe=0.34,
        roa=0.20,
    )
    db_session.add(f)
    db_session.commit()
    assert f.id is not None


def test_historical_financial_unique(db_session):
    db_session.add(
        HistoricalFinancial(
            stock_code="600519",
            period=date(2024, 12, 31),
            report_date=date(2025, 4, 3),
        )
    )
    db_session.commit()
    db_session.add(
        HistoricalFinancial(
            stock_code="600519",
            period=date(2024, 12, 31),
            report_date=date(2025, 4, 3),
        )
    )
    with pytest.raises(Exception):
        db_session.commit()


def test_historical_financial_report_date_indexed(db_session):
    """report_date index for point-in-time queries (where report_date <= day)."""
    table = HistoricalFinancial.__table__
    assert table.c.report_date.index


def test_historical_kline_composite_index(db_session):
    """Composite index on (stock_code, date) for range scans."""
    table = HistoricalKline.__table__
    indexes = {idx.name for idx in table.indexes}
    assert "ix_historical_klines_code_date" in indexes


def test_historical_valuation_partial_data_ok(db_session):
    """Most valuation fields are nullable (some stocks lack certain metrics)."""
    v = HistoricalValuation(
        stock_code="600519",
        date=date(2026, 6, 12),
        sp=100.0,  # only price, rest null
    )
    db_session.add(v)
    db_session.commit()
    assert v.pe_ttm is None
    assert v.pb is None


def test_historical_financial_period_granularity(db_session):
    """Both quarterly and annual periods stored."""
    db_session.add(
        HistoricalFinancial(
            stock_code="600519",
            period=date(2024, 9, 30),
            report_date=date(2024, 10, 26),
            report_type="third_quarterly_report",
        )
    )
    db_session.add(
        HistoricalFinancial(
            stock_code="600519",
            period=date(2024, 12, 31),
            report_date=date(2025, 4, 3),
            report_type="annual_report",
        )
    )
    db_session.commit()
    assert db_session.query(HistoricalFinancial).count() == 2
