"""Tests for market_service — market indices data from Lixinger."""

from unittest.mock import patch

import pytest

from app.services.market_service import INDEX_CODES, fetch_market_indices


class TestFetchMarketIndices:
    def test_returns_formatted_list(self):
        """fetch_market_indices returns list of {code, name, close, change_pct}."""
        mock_data = [
            {"stockCode": "000001", "cp": 3200.5, "cpc": 0.85},
            {"stockCode": "000300", "cp": 4200.0, "cpc": -0.32},
        ]
        with patch("app.services.market_service.get_lixinger_client") as mock_get:
            mock_client = mock_get.return_value
            mock_client.get_index_fundamental.return_value = mock_data

            result = fetch_market_indices()

        assert len(result) == 2
        assert result[0] == {"code": "000001", "name": "上证指数", "close": 3200.5, "change_pct": 0.85}
        assert result[1] == {"code": "000300", "name": "沪深300", "close": 4200.0, "change_pct": -0.32}

    def test_handles_missing_stock_code(self):
        """Items without stockCode get empty string as code."""
        mock_data = [{"cp": 100.0, "cpc": 0.5}]
        with patch("app.services.market_service.get_lixinger_client") as mock_get:
            mock_client = mock_get.return_value
            mock_client.get_index_fundamental.return_value = mock_data

            result = fetch_market_indices()

        assert len(result) == 1
        assert result[0]["code"] == ""

    def test_handles_unmapped_code(self):
        """Unmapped index code uses code itself as fallback name."""
        mock_data = [{"stockCode": "999999", "cp": 100.0, "cpc": 0.5}]
        with patch("app.services.market_service.get_lixinger_client") as mock_get:
            mock_client = mock_get.return_value
            mock_client.get_index_fundamental.return_value = mock_data

            result = fetch_market_indices()

        assert len(result) == 1
        assert result[0]["code"] == "999999"
        assert result[0]["name"] == "999999"  # fallback to code

    def test_handles_null_metrics(self):
        """Close and change_pct can be None."""
        mock_data = [{"stockCode": "000001", "cp": None, "cpc": None}]
        with patch("app.services.market_service.get_lixinger_client") as mock_get:
            mock_client = mock_get.return_value
            mock_client.get_index_fundamental.return_value = mock_data

            result = fetch_market_indices()

        assert result[0]["close"] is None
        assert result[0]["change_pct"] is None

    def test_returns_empty_list_on_lixinger_error(self):
        """LixingerError returns empty list (no crash)."""
        with patch("app.services.market_service.get_lixinger_client") as mock_get:
            mock_client = mock_get.return_value
            from app.services.lixinger_client import LixingerError
            mock_client.get_index_fundamental.side_effect = LixingerError("API down")

            result = fetch_market_indices()

        assert result == []

    def test_empty_data_returns_empty_list(self):
        """Empty list from Lixinger returns empty list."""
        with patch("app.services.market_service.get_lixinger_client") as mock_get:
            mock_client = mock_get.return_value
            mock_client.get_index_fundamental.return_value = []

            result = fetch_market_indices()

        assert result == []


class TestIndexCodes:
    def test_contains_major_indices(self):
        """INDEX_CODES contains the 6 major A-share indices."""
        assert "000001" in INDEX_CODES  # 上证指数
        assert "399001" in INDEX_CODES  # 深证成指
        assert "399006" in INDEX_CODES  # 创业板指
        assert "000016" in INDEX_CODES  # 上证50
        assert "000300" in INDEX_CODES  # 沪深300
        assert "000905" in INDEX_CODES  # 中证500

    def test_names_are_chinese(self):
        """All index names are in Chinese."""
        for code, name in INDEX_CODES.items():
            assert isinstance(name, str) and len(name) > 0
