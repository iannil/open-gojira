"""Test historical_data_pipeline — fetch + upsert for 3 tables."""
from datetime import date

import pytest

from app.models.historical_financial import HistoricalFinancial
from app.models.historical_kline import HistoricalKline
from app.models.historical_valuation import HistoricalValuation
from app.models.stock import Stock
from app.services.historical_data_pipeline import (
    fetch_and_upsert_financials,
    fetch_and_upsert_klines,
    fetch_and_upsert_valuations,
    run_historical_sync,
)


class MagicMockClient:
    """Fake Lixinger client returning canned data."""

    def __init__(self, kline_data=None, val_data=None, fin_data=None):
        self.kline_data = kline_data or []
        self.val_data = val_data or []
        self.fin_data = fin_data or []

    def get_kline(self, code, start, end=None, kline_type="lxr_fc_rights"):
        return self.kline_data

    def get_fundamentals(
        self, codes, date=None, start_date=None, end_date=None, metrics=None
    ):
        return self.val_data

    def get_financials(
        self,
        code,
        start_date=None,
        end_date=None,
        date=None,
        metrics=None,
        granularity="q",
    ):
        return self.fin_data


@pytest.fixture
def setup(db_session):
    db_session.add(Stock(code="600519", name="贵州茅台", exchange="sh"))
    db_session.flush()


# --- K-lines ---


def test_fetch_and_upsert_klines(db_session, setup, monkeypatch):
    fake = [
        {
            "date": "2024-01-02",
            "open": 1700, "high": 1710, "low": 1690, "close": 1705,
            "volume": 1000000, "amount": 1700000000, "to_r": 0.5,
        },
        {
            "date": "2024-01-03",
            "open": 1705, "high": 1720, "low": 1700, "close": 1715,
            "volume": 1100000, "amount": 1800000000, "to_r": 0.6,
        },
    ]
    from app.services import historical_data_pipeline as pl

    monkeypatch.setattr(
        pl, "get_lixinger_client", lambda: MagicMockClient(kline_data=fake)
    )

    count = fetch_and_upsert_klines(
        db_session, "600519",
        start_date="2024-01-01", end_date="2024-12-31",
    )
    db_session.commit()
    assert count == 2
    assert db_session.query(HistoricalKline).count() == 2


def test_fetch_klines_idempotent(db_session, setup, monkeypatch):
    """Re-running should not duplicate."""
    fake = [
        {"date": "2024-01-02", "open": 1, "high": 1, "low": 1, "close": 1},
    ]
    from app.services import historical_data_pipeline as pl

    monkeypatch.setattr(
        pl, "get_lixinger_client", lambda: MagicMockClient(kline_data=fake)
    )
    fetch_and_upsert_klines(
        db_session, "600519",
        start_date="2024-01-01", end_date="2024-12-31",
    )
    db_session.commit()
    count2 = fetch_and_upsert_klines(
        db_session, "600519",
        start_date="2024-01-01", end_date="2024-12-31",
    )
    db_session.commit()
    # All 1 records exist, count2 should be 0 new
    assert count2 == 0
    assert db_session.query(HistoricalKline).count() == 1


# --- Valuations ---


def test_fetch_and_upsert_valuations(db_session, setup, monkeypatch):
    fake = [
        {
            "stockCode": "600519", "date": "2024-01-02",
            "pe_ttm": 30, "pb": 10, "dyr": 0.025, "sp": 1700,
            "mc": 2100000000000,
        },
        {
            "stockCode": "600519", "date": "2024-01-03",
            "pe_ttm": 31, "pb": 10.5, "dyr": 0.024, "sp": 1720,
            "mc": 2150000000000,
        },
    ]
    monkeypatch.setattr(
        "app.services.historical_data_pipeline.get_lixinger_client",
        lambda: MagicMockClient(val_data=fake),
    )
    count = fetch_and_upsert_valuations(
        db_session, "600519",
        start_date="2024-01-01", end_date="2024-12-31",
    )
    db_session.commit()
    assert count == 2
    rows = db_session.query(HistoricalValuation).all()
    assert rows[0].sp == 1700


# --- Financials ---


def test_fetch_and_upsert_financials(db_session, setup, monkeypatch):
    fake = [
        {
            "stockCode": "600519", "date": "2024-03-31",
            "reportDate": "2024-04-26", "reportType": "first_quarterly_report",
            "revenue": 40000000000, "net_profit": 25000000000,
        },
        {
            "stockCode": "600519", "date": "2024-06-30",
            "reportDate": "2024-08-09", "reportType": "semi_annual_report",
            "revenue": 80000000000, "net_profit": 45000000000,
        },
    ]
    monkeypatch.setattr(
        "app.services.historical_data_pipeline.get_lixinger_client",
        lambda: MagicMockClient(fin_data=fake),
    )
    count = fetch_and_upsert_financials(
        db_session, "600519",
        start_date="2024-01-01", end_date="2024-12-31",
    )
    db_session.commit()
    assert count == 2
    rows = db_session.query(HistoricalFinancial).all()
    assert rows[0].report_date == date(2024, 4, 26)
    assert rows[0].revenue == 40000000000


# --- run_historical_sync (batch) ---


def test_run_historical_sync_batch(db_session, setup, monkeypatch):
    db_session.add(Stock(code="000001", name="平安银行", exchange="sz"))
    db_session.flush()
    monkeypatch.setattr(
        "app.services.historical_data_pipeline.get_lixinger_client",
        lambda: MagicMockClient(
            kline_data=[
                {"date": "2024-01-02", "open": 1, "high": 1, "low": 1, "close": 1},
            ],
            val_data=[{"stockCode": "600519", "date": "2024-01-02", "sp": 100}],
            fin_data=[
                {
                    "stockCode": "600519", "date": "2024-03-31",
                    "reportDate": "2024-04-26",
                },
            ],
        ),
    )
    summary = run_historical_sync(
        db_session, ["600519", "000001"],
        start_date="2024-01-01", end_date="2024-12-31",
    )
    db_session.commit()
    assert summary["klines"] >= 0
    assert summary["valuations"] >= 0
    assert summary["financials"] >= 0
    assert summary["errors"] == 0


def test_run_historical_sync_handles_errors(db_session, setup, monkeypatch):
    """One stock failure should not block others."""

    class FailClient:
        def get_kline(self, code, start, end=None, kline_type="lxr_fc_rights"):
            if code == "600519":
                raise RuntimeError("simulated failure")
            return [
                {"date": "2024-01-02", "open": 1, "high": 1, "low": 1, "close": 1},
            ]

        def get_fundamentals(self, *args, **kwargs):
            return []

        def get_financials(self, *args, **kwargs):
            return []

    monkeypatch.setattr(
        "app.services.historical_data_pipeline.get_lixinger_client",
        lambda: FailClient(),
    )
    db_session.add(Stock(code="000001", name="平安银行", exchange="sz"))
    db_session.flush()
    summary = run_historical_sync(
        db_session, ["600519", "000001"],
        start_date="2024-01-01", end_date="2024-12-31",
    )
    db_session.commit()
    assert summary["errors"] >= 1  # 600519 failed
    # 000001 still processed
    assert summary["klines"] >= 1
