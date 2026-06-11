"""Tests for kline_service — caching, incremental fetch, valuation bands."""

from datetime import date, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.price_kline import PriceKline
from app.models.stock import Stock
from app.services import kline_service


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    s = sessionmaker(bind=engine)()
    s.add(Stock(code="600519", name="贵州茅台"))
    s.commit()
    yield s
    s.close()


def test_get_klines_fetches_and_caches(db):
    end = date.today()
    start = end - timedelta(days=5)
    fake_raw = [
        {"date": (end - timedelta(days=d)).isoformat(),
         "open": 100 + d, "high": 105 + d, "low": 99 + d, "close": 102 + d, "volume": 1000}
        for d in range(5)
    ]

    class FakeClient:
        def __init__(self):
            self.calls = 0

        def get_kline(self, stock_code, start_date, end_date=None):
            self.calls += 1
            return fake_raw

    fake = FakeClient()
    with patch.object(kline_service, "get_lixinger_client", return_value=fake):
        rows1 = kline_service.get_klines(db, "600519", start=start, end=end)
        # Second call within range should not re-fetch the full window.
        rows2 = kline_service.get_klines(db, "600519", start=start, end=end)

    assert len(rows1) == 5
    assert len(rows2) == 5
    # First call writes 5 rows; second call only fetches the small refresh tail.
    assert db.query(PriceKline).count() == 5
    assert fake.calls == 2  # tail-refresh still issues a call, but is a no-op


def test_valuation_bands_assembles_implied_prices(db):
    end = date.today()
    start = end - timedelta(days=4)
    # 5 days of klines + matching fundamentals
    for i in range(5):
        d = end - timedelta(days=i)
        db.add(PriceKline(stock_code="600519", date=d, freq="day", close=100.0))
    db.commit()

    fake_fund = [
        {"date": (end - timedelta(days=i)).isoformat(), "pe_ttm": 10 + i, "sp": 100}
        for i in range(5)
    ]

    class FakeClient:
        def get_kline(self, **_):
            return []  # already cached

        def get_fundamentals(self, **_):
            return fake_fund

    with patch.object(kline_service, "get_lixinger_client", return_value=FakeClient()):
        bands = kline_service.get_valuation_bands(db, "600519", metric="pe_ttm", years=1)

    assert len(bands["dates"]) == 5
    assert bands["metric"] == "pe_ttm"
    labels = [b["label"] for b in bands["band_levels"]]
    assert labels == ["p10", "p50", "p90"]
    # Every band level has implied_close of same length
    for lbl in labels:
        assert len(bands["implied_close"][lbl]) == 5
