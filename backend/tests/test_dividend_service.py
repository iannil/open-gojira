"""Tests for dividend_service — CRUD, summary aggregation, and Lixinger sync.

Covers: create, read, update, delete, list filtering, summary aggregation by
year and stock, and the fetch-and-store-from-Lixinger integration path.
"""

from datetime import date
from unittest.mock import patch

import pytest

from app.models.dividend import DividendRecord
from app.models.stock import Stock
from app.services.dividend_service import (
    create_dividend_record,
    delete_dividend_record,
    get_dividend_record,
    get_dividend_summary,
    list_dividend_records,
    update_dividend_record,
    fetch_and_store_from_lixinger,
)


def _ensure_stock(db, code="600519", name="Test Stock"):
    """Ensure a Stock row exists (dividend_service requires FK to stock table)."""
    existing = db.query(Stock).filter(Stock.code == code).first()
    if not existing:
        s = Stock(code=code, name=name, industry="测试行业", listed_date=date(2000, 1, 1))
        db.add(s)
        db.flush()


def _seed_dividend(db, stock_code="600519", year=2024, amount=2.0, qty=100):
    """Helper to create a dividend record with default values."""
    _ensure_stock(db, code=stock_code)
    return create_dividend_record(db, {
        "stock_code": stock_code,
        "ex_date": date(year, 6, 15),
        "amount_per_share": amount,
        "quantity_held": qty,
        "total_received": amount * qty,
        "reinvested": False,
    })


class TestDividendCRUD:
    def test_create_dividend(self, db_session):
        rec = _seed_dividend(db_session)
        db_session.commit()
        assert rec.id is not None
        assert rec.stock_code == "600519"
        assert rec.amount_per_share == 2.0
        assert rec.total_received == 200.0

    def test_get_dividend(self, db_session):
        rec = _seed_dividend(db_session)
        db_session.commit()
        fetched = get_dividend_record(db_session, rec.id)
        assert fetched is not None
        assert fetched.id == rec.id
        assert fetched.stock_code == "600519"

    def test_get_dividend_not_found(self, db_session):
        fetched = get_dividend_record(db_session, 9999)
        assert fetched is None

    def test_update_dividend(self, db_session):
        rec = _seed_dividend(db_session, amount=2.0, qty=100)
        db_session.commit()
        updated = update_dividend_record(db_session, rec.id, {
            "amount_per_share": 2.5,
            "total_received": 250.0,
        })
        assert updated is not None
        assert updated.amount_per_share == 2.5
        assert updated.total_received == 250.0

    def test_update_not_found(self, db_session):
        updated = update_dividend_record(db_session, 9999, {"total_received": 100.0})
        assert updated is None

    def test_delete_dividend(self, db_session):
        rec = _seed_dividend(db_session)
        db_session.commit()
        deleted = delete_dividend_record(db_session, rec.id)
        assert deleted is True
        assert get_dividend_record(db_session, rec.id) is None

    def test_delete_not_found(self, db_session):
        deleted = delete_dividend_record(db_session, 9999)
        assert deleted is False


class TestDividendList:
    def test_list_all(self, db_session):
        _seed_dividend(db_session, stock_code="600519")
        _seed_dividend(db_session, stock_code="000858")
        db_session.commit()
        records = list_dividend_records(db_session)
        assert len(records) == 2

    def test_list_filter_by_stock(self, db_session):
        _seed_dividend(db_session, stock_code="600519")
        _seed_dividend(db_session, stock_code="000858")
        _seed_dividend(db_session, stock_code="600519")
        db_session.commit()
        records = list_dividend_records(db_session, stock_code="600519")
        assert len(records) == 2
        assert all(r.stock_code == "600519" for r in records)

    def test_list_empty_when_no_match(self, db_session):
        records = list_dividend_records(db_session, stock_code="NONEXIST")
        assert records == []


class TestDividendSummary:
    def test_summary_total_cumulative(self, db_session):
        """total_cumulative sums all total_received across records."""
        _seed_dividend(db_session, stock_code="600519", amount=2.0, qty=100)  # 200
        _seed_dividend(db_session, stock_code="000858", amount=1.5, qty=200)  # 300
        _seed_dividend(db_session, stock_code="600519", amount=1.0, qty=50)   # 50
        db_session.commit()
        summary = get_dividend_summary(db_session)
        assert summary["total_cumulative"] == pytest.approx(550.0)

    def test_summary_by_year(self, db_session):
        """by_year groups records by year with total and count."""
        _seed_dividend(db_session, stock_code="600519", year=2023, amount=2.0, qty=100)
        _seed_dividend(db_session, stock_code="000858", year=2024, amount=1.5, qty=200)
        _seed_dividend(db_session, stock_code="600519", year=2024, amount=1.0, qty=50)
        db_session.commit()
        summary = get_dividend_summary(db_session)
        assert len(summary["by_year"]) == 2
        year_map = {y["year"]: y for y in summary["by_year"]}
        assert year_map[2023]["total_received"] == pytest.approx(200.0)
        assert year_map[2023]["count"] == 1
        assert year_map[2024]["total_received"] == pytest.approx(350.0)
        assert year_map[2024]["count"] == 2

    def test_summary_by_stock(self, db_session):
        """by_stock groups records by stock_code with total, count, and yield."""
        _seed_dividend(db_session, stock_code="600519", amount=2.0, qty=100)  # 200
        _seed_dividend(db_session, stock_code="600519", amount=1.0, qty=50)   # 50
        _seed_dividend(db_session, stock_code="000858", amount=1.5, qty=200)  # 300
        db_session.commit()
        summary = get_dividend_summary(db_session)
        assert len(summary["by_stock"]) == 2
        stock_map = {s["stock_code"]: s for s in summary["by_stock"]}
        assert stock_map["600519"]["total_received"] == pytest.approx(250.0)
        assert stock_map["600519"]["count"] == 2
        assert stock_map["000858"]["total_received"] == pytest.approx(300.0)
        assert stock_map["000858"]["count"] == 1

    def test_summary_empty(self, db_session):
        """summary with no records returns zeros and empty lists."""
        summary = get_dividend_summary(db_session)
        assert summary["total_cumulative"] == 0.0
        assert summary["by_year"] == []
        assert summary["by_stock"] == []


class TestDividendSync:
    def test_fetch_and_store_lixinger_calls_client(self, db_session):
        """fetch_and_store_from_lixinger delegates to the lixinger client."""
        _ensure_stock(db_session, code="600519")
        db_session.commit()
        mock_data = [
            {
                "stockCode": "600519",
                "exDate": "2024-06-15",
                "dividend": 2.0,
            },
        ]
        with patch("app.services.dividend_service.get_lixinger_client") as mock_get:
            mock_client = mock_get.return_value
            mock_client.get_dividend.return_value = mock_data
            count = fetch_and_store_from_lixinger(db_session, "600519", years=5)

        assert count == 1
        records = list_dividend_records(db_session)
        assert len(records) == 1
        assert records[0].stock_code == "600519"
        assert records[0].amount_per_share == 2.0
