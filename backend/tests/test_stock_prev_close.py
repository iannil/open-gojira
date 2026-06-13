"""Test Stock.prev_close field + sync."""
from datetime import date
import pytest

from app.models.stock import Stock
from app.services.kline_service import update_prev_close_for_stock, update_prev_close_batch


def test_stock_has_prev_close_field(db_session):
    s = Stock(code="600519", name="贵州茅台", exchange="sh", prev_close=1680.0)
    db_session.add(s)
    db_session.commit()
    refreshed = db_session.get(Stock, "600519")
    assert refreshed.prev_close == 1680.0


def test_prev_close_nullable(db_session):
    s = Stock(code="600519", name="贵州茅台", exchange="sh")
    db_session.add(s)
    db_session.commit()
    assert db_session.get(Stock, "600519").prev_close is None


def test_update_prev_close_for_stock(db_session, monkeypatch):
    """Sync prev_close from latest K-line."""
    db_session.add(Stock(code="600519", name="贵州茅台", exchange="sh"))
    db_session.flush()

    # Mock kline client — Lixinger returns newest-first (validated S0 spike A7)
    fake_klines = [
        {"date": "2026-06-11", "close": 1680.0},  # latest (newest first)
        {"date": "2026-06-10", "close": 1670.0},
    ]
    from app.services import kline_service
    class FakeClient:
        def get_kline(self, code, start, end=None):
            return fake_klines
    monkeypatch.setattr(kline_service, "get_lixinger_client", lambda: FakeClient())

    updated = update_prev_close_for_stock(db_session, "600519")
    assert updated is True
    assert db_session.get(Stock, "600519").prev_close == 1680.0


def test_update_prev_close_no_kline_data(db_session, monkeypatch):
    """If no K-line data, leave prev_close unchanged."""
    db_session.add(Stock(code="600519", name="贵州茅台", exchange="sh", prev_close=1500.0))
    db_session.flush()

    from app.services import kline_service
    class FakeClient:
        def get_kline(self, code, start, end=None):
            return []
    monkeypatch.setattr(kline_service, "get_lixinger_client", lambda: FakeClient())

    updated = update_prev_close_for_stock(db_session, "600519")
    assert updated is False
    # prev_close 不变
    assert db_session.get(Stock, "600519").prev_close == 1500.0


def test_update_prev_close_batch(db_session, monkeypatch):
    """Batch update multiple stocks."""
    db_session.add(Stock(code="600519", name="茅台", exchange="sh"))
    db_session.add(Stock(code="000001", name="平安银行", exchange="sz"))
    db_session.flush()

    klines = {
        "600519": [{"date": "2026-06-11", "close": 1680.0}],
        "000001": [{"date": "2026-06-11", "close": 15.0}],
    }
    from app.services import kline_service
    class FakeClient:
        def get_kline(self, code, start, end=None):
            return klines.get(code, [])
    monkeypatch.setattr(kline_service, "get_lixinger_client", lambda: FakeClient())

    count = update_prev_close_batch(db_session, ["600519", "000001"])
    assert count == 2
    assert db_session.get(Stock, "600519").prev_close == 1680.0
    assert db_session.get(Stock, "000001").prev_close == 15.0
