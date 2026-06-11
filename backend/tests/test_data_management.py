"""Tests for data_management_service and data_quality_service."""

import pytest
from datetime import date, timedelta
from sqlalchemy.orm import Session

from tests.conftest import TestSessionLocal

from app.models.dividend import DividendRecord
from app.models.financial import FinancialStatement
from app.models.holding import Holding
from app.models.price_kline import PriceKline
from app.models.stock import Stock
from app.models.valuation import ValuationSnapshot
from app.models.watchlist import WatchlistGroup, WatchlistItem


@pytest.fixture
def db():
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


def _seed_stock(db: Session, code: str = "000001", name: str = "测试股票") -> Stock:
    s = Stock(code=code, name=name, industry="银行")
    db.add(s)
    db.commit()
    return s


def _seed_watchlist(db: Session, stock_code: str) -> None:
    group = db.query(WatchlistGroup).filter(WatchlistGroup.name == "默认").first()
    if not group:
        group = WatchlistGroup(name="默认")
        db.add(group)
        db.flush()
    item = WatchlistItem(group_id=group.id, stock_code=stock_code)
    db.add(item)
    db.commit()


def _seed_holding(db: Session, stock_code: str) -> None:
    h = Holding(stock_code=stock_code, buy_date=date(2026, 1, 1),
                buy_price=10.0, quantity=100, stop_profit_price=15.0)
    db.add(h)
    db.commit()


def _seed_valuation(db: Session, stock_code: str, d: date) -> None:
    db.add(ValuationSnapshot(stock_code=stock_code, date=d, pe_ttm=10.0, pb=1.0))
    db.commit()


class TestGetWatchedStockCodes:
    def test_returns_empty_when_nothing_watched(self, db: Session):
        from app.services.data_management_service import get_watched_stock_codes
        assert get_watched_stock_codes(db) == set()

    def test_returns_watched_codes(self, db: Session):
        _seed_stock(db, "000001")
        _seed_watchlist(db, "000001")
        from app.services.data_management_service import get_watched_stock_codes
        assert get_watched_stock_codes(db) == {"000001"}

    def test_returns_held_codes(self, db: Session):
        _seed_stock(db, "600519")
        _seed_holding(db, "600519")
        from app.services.data_management_service import get_watched_stock_codes
        assert get_watched_stock_codes(db) == {"600519"}

    def test_returns_union(self, db: Session):
        _seed_stock(db, "000001")
        _seed_stock(db, "600519")
        _seed_watchlist(db, "000001")
        _seed_holding(db, "600519")
        from app.services.data_management_service import get_watched_stock_codes
        assert get_watched_stock_codes(db) == {"000001", "600519"}


class TestSearchStocks:
    def test_search_empty_keyword(self, db: Session):
        from app.services.data_management_service import search_stocks
        assert search_stocks(db, "") == []

    def test_search_by_code(self, db: Session):
        _seed_stock(db, "000001", "平安银行")
        from app.services.data_management_service import search_stocks
        results = search_stocks(db, "000001")
        assert len(results) == 1
        assert results[0]["code"] == "000001"

    def test_search_by_name(self, db: Session):
        _seed_stock(db, "000001", "平安银行")
        from app.services.data_management_service import search_stocks
        results = search_stocks(db, "平安")
        assert len(results) == 1

    def test_search_escapes_percent_wildcard(self, db: Session):
        _seed_stock(db, "000001", "test%stock")
        _seed_stock(db, "000002", "testastock")
        from app.services.data_management_service import search_stocks
        # Searching for literal "%" should only match "test%stock", not "testastock"
        results = search_stocks(db, "%")
        assert len(results) == 1
        assert results[0]["code"] == "000001"

    def test_search_escapes_underscore_wildcard(self, db: Session):
        _seed_stock(db, "000001", "test_stock")
        _seed_stock(db, "000002", "testXstock")
        from app.services.data_management_service import search_stocks
        # Searching for literal "_" should only match "test_stock", not "testXstock"
        results = search_stocks(db, "_")
        assert len(results) == 1
        assert results[0]["code"] == "000001"


class TestStockPool:
    def test_list_empty_pool(self, db: Session):
        from app.services.data_management_service import list_stock_pool
        assert list_stock_pool(db) == []

    def test_list_pool_with_completeness(self, db: Session):
        _seed_stock(db, "000001")
        _seed_watchlist(db, "000001")
        _seed_valuation(db, "000001", date(2026, 6, 1))

        from app.services.data_management_service import list_stock_pool
        results = list_stock_pool(db)
        assert len(results) == 1
        assert results[0]["data_completeness"]["has_valuation"] is True
        assert results[0]["data_completeness"]["has_financial"] is False

    def test_add_to_pool(self, db: Session):
        _seed_stock(db, "000001")
        from app.services.data_management_service import add_to_pool
        added = add_to_pool(db, ["000001"])
        assert added >= 1

    def test_remove_from_pool(self, db: Session):
        _seed_stock(db, "000001")
        _seed_watchlist(db, "000001")
        from app.services.data_management_service import remove_from_pool
        removed = remove_from_pool(db, ["000001"])
        assert removed == 1


class TestDataStatus:
    def test_status_empty(self, db: Session):
        from app.services.data_management_service import get_data_status
        status = get_data_status(db)
        assert status["valuations"]["total_records"] == 0

    def test_status_with_data(self, db: Session):
        _seed_stock(db, "000001")
        _seed_watchlist(db, "000001")
        _seed_valuation(db, "000001", date(2026, 6, 1))

        from app.services.data_management_service import get_data_status
        status = get_data_status(db)
        assert status["valuations"]["total_records"] == 1
        assert status["valuations"]["latest_date"] == "2026-06-01"


class TestCleanup:
    def test_preview_empty(self, db: Session):
        from app.services.data_management_service import preview_cleanup
        result = preview_cleanup(db, "valuations")
        assert result["record_count"] == 0

    def test_preview_with_data(self, db: Session):
        _seed_stock(db, "000001")
        _seed_valuation(db, "000001", date(2025, 1, 1))
        _seed_valuation(db, "000001", date(2026, 6, 1))

        from app.services.data_management_service import preview_cleanup
        result = preview_cleanup(db, "valuations", before_date="2026-01-01")
        assert result["record_count"] == 1

    def test_execute_cleanup(self, db: Session):
        _seed_stock(db, "000001")
        _seed_valuation(db, "000001", date(2025, 1, 1))
        _seed_valuation(db, "000001", date(2026, 6, 1))

        from app.services.data_management_service import execute_cleanup
        result = execute_cleanup(db, "valuations", before_date="2026-01-01")
        assert result["deleted_count"] == 1

        remaining = db.query(ValuationSnapshot).count()
        assert remaining == 1

    def test_cleanup_invalid_data_type(self, db: Session):
        from app.services.data_management_service import execute_cleanup
        with pytest.raises(ValueError, match="Unknown data type"):
            execute_cleanup(db, "invalid_type")


class TestDataQuality:
    def test_quality_empty_pool(self, db: Session):
        from app.services.data_quality_service import compute_quality
        result = compute_quality(db)
        assert result.overall_score == 0
        assert "股票池为空" in result.recommendations[0]

    def test_quality_with_partial_data(self, db: Session):
        _seed_stock(db, "000001")
        _seed_watchlist(db, "000001")
        _seed_valuation(db, "000001", date(2026, 6, 9))

        from app.services.data_quality_service import compute_quality
        result = compute_quality(db)
        assert result.overall_score > 0
        assert "valuations" in result.data_types

    def test_quality_missing_recommendation(self, db: Session):
        _seed_stock(db, "000001")
        _seed_watchlist(db, "000001")

        from app.services.data_quality_service import compute_quality
        result = compute_quality(db)
        assert any("缺失" in r for r in result.recommendations)

    def test_freshness_fresh(self):
        from app.services.data_quality_service import _compute_freshness
        assert _compute_freshness(date.today() - timedelta(days=1), "valuations") == "fresh"

    def test_freshness_stale(self):
        from app.services.data_quality_service import _compute_freshness
        # 5 days ago, within stale threshold (7 days) for valuations
        assert _compute_freshness(date.today() - timedelta(days=5), "valuations") == "stale"

    def test_freshness_missing_when_too_old(self):
        from app.services.data_quality_service import _compute_freshness
        # > 7 days for valuations → missing
        assert _compute_freshness(date.today() - timedelta(days=30), "valuations") == "missing"

    def test_freshness_none(self):
        from app.services.data_quality_service import _compute_freshness
        assert _compute_freshness(None, "valuations") == "missing"

    def test_detect_gaps_no_codes(self, db: Session):
        from app.services.data_quality_service import _detect_gaps
        assert _detect_gaps(db, ValuationSnapshot, "date", "stock_code", set()) == 0

    def test_detect_gaps_no_gaps(self, db: Session):
        _seed_stock(db, "000001")
        _seed_watchlist(db, "000001")
        _seed_valuation(db, "000001", date(2026, 6, 7))
        _seed_valuation(db, "000001", date(2026, 6, 9))

        from app.services.data_quality_service import _detect_gaps
        gaps = _detect_gaps(db, ValuationSnapshot, "date", "stock_code", {"000001"})
        # Same 2 dates exist for this stock → gap = 0
        assert gaps == 0

    def test_detect_gaps_with_missing(self, db: Session):
        _seed_stock(db, "000001")
        _seed_stock(db, "000002")
        _seed_watchlist(db, "000001")
        _seed_watchlist(db, "000002")
        _seed_valuation(db, "000001", date(2026, 6, 7))
        _seed_valuation(db, "000001", date(2026, 6, 8))
        _seed_valuation(db, "000001", date(2026, 6, 9))
        _seed_valuation(db, "000002", date(2026, 6, 7))
        _seed_valuation(db, "000002", date(2026, 6, 9))
        # 000002 is missing 6/8 → gap = 1

        from app.services.data_quality_service import _detect_gaps
        gaps = _detect_gaps(db, ValuationSnapshot, "date", "stock_code", {"000001", "000002"})
        assert gaps == 1
