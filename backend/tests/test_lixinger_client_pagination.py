"""Test pagination + time window handling in LixingerClient."""
from unittest.mock import patch, MagicMock
from app.services.lixinger_client import LixingerClient


def test_get_company_list_all_paginates_through_full_market():
    """When page_size > 500 (Lixinger's silent cap), should loop pages."""
    client = LixingerClient(token="fake")

    # Mock _post to simulate Lixinger's silent 500 cap
    # Page 0: 500 records, Page 1: 500, Page 2: 500, ..., Page 11: 125 (last)
    def fake_post(path, payload, cache_ttl=0):
        page = payload.get("pageIndex", 0)
        # Lixinger caps at 500 regardless of pageSize
        page_size = min(payload.get("pageSize", 500), 500)
        if page < 11:
            return [{"stockCode": f"{page:02d}{i:04d}"} for i in range(page_size)]
        elif page == 11:
            return [{"stockCode": f"11{i:04d}"} for i in range(125)]
        else:
            return []

    with patch.object(client, "_post", side_effect=fake_post):
        result = client.get_company_list_all()

    assert len(result) == 11 * 500 + 125  # = 5625


def test_get_company_list_all_stops_on_empty_page():
    """Stop pagination when a page returns empty."""
    client = LixingerClient(token="fake")

    def fake_post(path, payload, cache_ttl=0):
        page = payload.get("pageIndex", 0)
        if page == 0:
            return [{"stockCode": f"{i:04d}"} for i in range(100)]
        return []

    with patch.object(client, "_post", side_effect=fake_post):
        result = client.get_company_list_all()

    assert len(result) == 100


def test_get_dividend_full_segments_long_ranges():
    """Range > 10 years should be split into multiple API calls."""
    client = LixingerClient(token="fake")

    calls = []
    def fake_post(path, payload, cache_ttl=0):
        calls.append(payload)
        # Return 1 record per segment for verification
        return [{"date": payload["startDate"]}]

    with patch.object(client, "_post", side_effect=fake_post):
        # 15 years should split into 2 segments
        result = client.get_dividend_full("600519", "2010-01-01", "2025-01-01")

    assert len(calls) == 2  # 2010-01-01..2019-12-30 + 2019-12-31..2025-01-01
    assert len(result) == 2
    # First segment starts at 2010-01-01
    assert calls[0]["startDate"] == "2010-01-01"
    # Second segment starts after first segment's end
    assert calls[1]["startDate"] > "2019-12-30"


def test_get_dividend_full_short_range_no_split():
    """Range < 10 years should be a single call."""
    client = LixingerClient(token="fake")

    calls = []
    def fake_post(path, payload, cache_ttl=0):
        calls.append(payload)
        return [{"date": "2022-01-01"}]

    with patch.object(client, "_post", side_effect=fake_post):
        result = client.get_dividend_full("600519", "2020-01-01", "2024-01-01")

    assert len(calls) == 1
    assert len(result) == 1


def test_get_dividend_full_handles_empty_response():
    client = LixingerClient(token="fake")

    with patch.object(client, "_post", return_value=[]):
        result = client.get_dividend_full("600519", "2010-01-01", "2024-01-01")

    assert result == []
