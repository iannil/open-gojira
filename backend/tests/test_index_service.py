"""Tests for index_service — benchmark index kline sync, query, and return computation."""

from datetime import date, timedelta
from unittest.mock import patch

import pytest

from app.models.index_kline import IndexKline
from app.services.index_service import (
    DEFAULT_BENCHMARK,
    _float,
    compute_benchmark_return,
    get_index_kline_range,
    sync_index_klines,
)


class TestFloatHelper:
    def test_float_converts_number(self):
        assert _float(42) == 42.0

    def test_float_converts_string(self):
        assert _float("3.14") == 3.14

    def test_float_returns_none(self):
        assert _float(None) is None


class TestSyncIndexKlines:
    def test_inserts_new_klines(self, db_session):
        """sync_index_klines inserts klines from mock Lixinger data."""
        today = date.today()
        mock_data = [
            {"date": (today - timedelta(days=2)).isoformat(), "open": 4000.0, "high": 4010.0, "low": 3990.0, "close": 4005.0, "volume": 1e9},
            {"date": (today - timedelta(days=1)).isoformat(), "open": 4005.0, "high": 4020.0, "low": 3995.0, "close": 4010.0, "volume": 1.1e9},
        ]

        with patch("app.services.index_service.LixingerClient") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.get_index_kline.return_value = mock_data

            result = sync_index_klines(db_session, index_code="000300")

        assert result["inserted"] == 2
        assert result["updated"] == 0
        assert result["index_code"] == "000300"

        rows = db_session.query(IndexKline).all()
        assert len(rows) == 2
        assert rows[0].index_code == "000300"
        assert rows[0].close == 4005.0

    def test_updates_existing_kline(self, db_session):
        """Existing kline for same index+date is updated, not duplicated."""
        today = date.today()
        # Seed existing row
        db_session.add(IndexKline(
            index_code="000300", date=today,
            open=100.0, high=110.0, low=90.0, close=105.0, volume=1e9,
        ))
        db_session.commit()

        mock_data = [
            {"date": today.isoformat(), "open": 200.0, "high": 210.0, "low": 190.0, "close": 205.0, "volume": 2e9},
        ]

        with patch("app.services.index_service.LixingerClient") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.get_index_kline.return_value = mock_data

            result = sync_index_klines(db_session, index_code="000300")

        assert result["inserted"] == 0
        assert result["updated"] == 1

        rows = db_session.query(IndexKline).all()
        assert len(rows) == 1  # no duplicate
        assert rows[0].close == 205.0  # updated

    def test_no_data_returns_zero(self, db_session):
        """When Lixinger returns empty, no rows are inserted."""
        with patch("app.services.index_service.LixingerClient") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.get_index_kline.return_value = []

            result = sync_index_klines(db_session)

        assert result["inserted"] == 0
        assert result["updated"] == 0
        assert db_session.query(IndexKline).count() == 0

    def test_skips_items_without_date(self, db_session):
        """Kline items missing a date field are skipped."""
        mock_data = [
            {"open": 100.0, "close": 105.0},  # no date
        ]
        with patch("app.services.index_service.LixingerClient") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.get_index_kline.return_value = mock_data

            result = sync_index_klines(db_session)

        assert result["inserted"] == 0


class TestGetIndexKlineRange:
    def test_returns_klines_in_date_order(self, db_session):
        """get_index_kline_range returns klines ordered by date ascending."""
        dates = [
            date(2024, 1, 3),
            date(2024, 1, 1),
            date(2024, 1, 2),
        ]
        for d in dates:
            db_session.add(IndexKline(
                index_code="000300", date=d,
                open=100.0, close=100.0, high=100.0, low=100.0, volume=0,
            ))
        db_session.commit()

        rows = get_index_kline_range(db_session, "000300")
        assert len(rows) == 3
        assert [r.date for r in rows] == [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)]

    def test_filters_by_date_range(self, db_session):
        """start_date and end_date filter correctly."""
        for d in range(1, 6):
            db_session.add(IndexKline(
                index_code="000300", date=date(2024, 1, d),
                open=100.0, close=100.0, high=100.0, low=100.0, volume=0,
            ))
        db_session.commit()

        rows = get_index_kline_range(db_session, "000300", start_date=date(2024, 1, 2), end_date=date(2024, 1, 4))
        assert len(rows) == 3
        assert rows[0].date == date(2024, 1, 2)
        assert rows[-1].date == date(2024, 1, 4)

    def test_empty_when_no_match(self, db_session):
        rows = get_index_kline_range(db_session, "000300", start_date=date(2099, 1, 1))
        assert rows == []


class TestComputeBenchmarkReturn:
    def test_computes_return(self, db_session):
        """compute_benchmark_return calculates close-to-close return."""
        db_session.add(IndexKline(
            index_code="000300", date=date(2024, 1, 1),
            open=100.0, close=100.0, high=100.0, low=100.0, volume=0,
        ))
        db_session.add(IndexKline(
            index_code="000300", date=date(2024, 6, 1),
            open=100.0, close=110.0, high=110.0, low=100.0, volume=0,
        ))
        db_session.commit()

        ret = compute_benchmark_return(db_session, "000300", start_date=date(2024, 1, 1))
        assert ret is not None
        assert ret == pytest.approx(0.10)  # 110/100 - 1 = 10%

    def test_returns_none_with_insufficient_data(self, db_session):
        """Less than 2 klines returns None."""
        db_session.add(IndexKline(
            index_code="000300", date=date(2024, 1, 1),
            open=100.0, close=100.0, high=100.0, low=100.0, volume=0,
        ))
        db_session.commit()

        ret = compute_benchmark_return(db_session, "000300", start_date=date(2024, 1, 1))
        assert ret is None

    def test_returns_none_with_zero_close(self, db_session):
        """Zero close price returns None (division by zero guard)."""
        db_session.add(IndexKline(
            index_code="000300", date=date(2024, 1, 1),
            open=0.0, close=0.0, high=0.0, low=0.0, volume=0,
        ))
        db_session.add(IndexKline(
            index_code="000300", date=date(2024, 6, 1),
            open=0.0, close=110.0, high=110.0, low=0.0, volume=0,
        ))
        db_session.commit()

        ret = compute_benchmark_return(db_session, "000300", start_date=date(2024, 1, 1))
        assert ret is None

    def test_negative_return(self, db_session):
        """Negative return is correctly computed."""
        db_session.add(IndexKline(
            index_code="000300", date=date(2024, 1, 1),
            open=100.0, close=100.0, high=100.0, low=100.0, volume=0,
        ))
        db_session.add(IndexKline(
            index_code="000300", date=date(2024, 6, 1),
            open=100.0, close=90.0, high=100.0, low=90.0, volume=0,
        ))
        db_session.commit()

        ret = compute_benchmark_return(db_session, "000300", start_date=date(2024, 1, 1))
        assert ret is not None
        assert ret == pytest.approx(-0.10)
