"""Tests for fetch_and_store_financials granularity argument + raw_data control."""

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models.financial import FinancialStatement
from app.models.stock import Stock
from app.services import financial_service


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    s = sessionmaker(bind=engine)()
    s.add(Stock(code="600519", name="贵州茅台"))
    s.commit()
    yield s
    s.close()


class _FakeClient:
    def __init__(self, captured_metrics: list[str]):
        self.captured_metrics = captured_metrics
        self.captured_granularity = None

    def get_financials(self, stock_code, metrics=None, granularity="y", **kw):
        self.captured_metrics[:] = metrics or []
        self.captured_granularity = granularity
        # Return one fake period
        return [
            {
                "date": "2024-09-30",
                granularity: {
                    "ps": {"toi": {"t": 1000.0}, "np": {"t": 200.0}},
                    "bs": {"ta": {"t": 5000.0}},
                    "cfs": {"ncffoa": {"t": 250.0}},
                    "m": {"wroe": {"t": 18.0}},
                },
            }
        ]


def test_default_granularity_is_annual(db: Session):
    metrics: list[str] = []
    fake = _FakeClient(metrics)
    with patch.object(financial_service, "get_lixinger_client", return_value=fake):
        financial_service.fetch_and_store_financials(db, "600519")
    assert all(m.startswith("y.") for m in metrics)
    row = db.query(FinancialStatement).first()
    assert row.report_type == "annual"


def test_quarterly_granularity_uses_q_metrics(db: Session):
    metrics: list[str] = []
    fake = _FakeClient(metrics)
    with patch.object(financial_service, "get_lixinger_client", return_value=fake):
        financial_service.fetch_and_store_financials(db, "600519", granularity="q")
    assert all(m.startswith("q.") for m in metrics)
    row = db.query(FinancialStatement).first()
    assert row.report_type == "quarterly"


def test_raw_data_not_stored_by_default(db: Session):
    fake = _FakeClient([])
    with patch.object(financial_service, "get_lixinger_client", return_value=fake):
        financial_service.fetch_and_store_financials(db, "600519")
    row = db.query(FinancialStatement).first()
    assert row.raw_data is None


def test_raw_data_stored_when_requested(db: Session):
    fake = _FakeClient([])
    with patch.object(financial_service, "get_lixinger_client", return_value=fake):
        financial_service.fetch_and_store_financials(db, "600519", store_raw=True)
    row = db.query(FinancialStatement).first()
    assert row.raw_data is not None
