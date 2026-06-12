"""Tests for data_service (Lixinger-backed)."""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.services.data_service import (
    fetch_current_price,
    fetch_pe_pb_history,
    fetch_stock_info,
)
from app.services.lixinger_client import LixingerError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


# ---------------------------------------------------------------------------
# data_service tests — mocked Lixinger client
# ---------------------------------------------------------------------------

class TestFetchStockInfo:
    """Tests for fetch_stock_info."""

    @patch("app.services.data_service.get_lixinger_client")
    def test_returns_normalized_dict(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.get_company_profile.return_value = None
        mock_client.get_company_list_all.return_value = [
            {"stockCode": "000001", "name": "平安银行"},
            {"stockCode": "600519", "name": "贵州茅台"},
        ]

        result = fetch_stock_info("600519")
        assert result is not None
        assert result["code"] == "600519"
        assert result["name"] == "贵州茅台"

    @patch("app.services.data_service.get_lixinger_client")
    def test_uses_profile_first(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.get_company_profile.return_value = {
            "name": "贵州茅台",
            "industry": "白酒",
        }

        result = fetch_stock_info("600519")
        assert result is not None
        assert result["name"] == "贵州茅台"
        assert result["industry"] == "白酒"
        mock_client.get_company_list_all.assert_not_called()

    @patch("app.services.data_service.get_lixinger_client")
    def test_returns_none_when_lixinger_raises(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.get_company_profile.side_effect = LixingerError("API error")

        result = fetch_stock_info("600519")
        assert result is None

    @patch("app.services.data_service.get_lixinger_client")
    def test_returns_none_for_empty_response(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.get_company_profile.return_value = None
        mock_client.get_company_list_all.return_value = []

        result = fetch_stock_info("600519")
        assert result is None


class TestFetchPePbHistory:
    """Tests for fetch_pe_pb_history."""

    @patch("app.services.data_service.get_lixinger_client")
    def test_returns_history_list(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.get_fundamentals.return_value = [
            {"date": "2024-01-15T00:00:00+08:00", "pe_ttm": 35.2, "pb": 12.5},
            {"date": "2024-02-15T00:00:00+08:00", "pe_ttm": 33.8, "pb": 11.9},
            {"date": "2024-03-15T00:00:00+08:00", "pe_ttm": 36.1, "pb": 13.0},
        ]

        result = fetch_pe_pb_history("600519", years=10)
        assert len(result) == 3
        assert result[0]["date"] == "2024-01-15"
        assert result[0]["pe_ttm"] == 35.2
        assert result[0]["pb"] == 12.5

    @patch("app.services.data_service.get_lixinger_client")
    def test_returns_empty_on_error(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.get_fundamentals.side_effect = LixingerError("API error")

        result = fetch_pe_pb_history("600519")
        assert result == []

    @patch("app.services.data_service.get_lixinger_client")
    def test_returns_empty_for_empty_data(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.get_fundamentals.return_value = []

        result = fetch_pe_pb_history("600519")
        assert result == []


class TestFetchCurrentPrice:
    """Tests for fetch_current_price."""

    @patch("app.services.data_service.get_lixinger_client")
    def test_returns_price(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.get_fundamentals.return_value = [
            {"sp": 1800.50},
        ]

        result = fetch_current_price("600519")
        assert result == 1800.50

    @patch("app.services.data_service.get_lixinger_client")
    def test_returns_none_for_unknown_code(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.get_fundamentals.return_value = []

        result = fetch_current_price("999999")
        assert result is None

    @patch("app.services.data_service.get_lixinger_client")
    def test_returns_none_on_error(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.get_fundamentals.side_effect = LixingerError("API error")

        result = fetch_current_price("600519")
        assert result is None


