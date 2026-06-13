"""Test GET /api/stocks/{code}/price-band endpoint."""
import pytest

from app.models.stock import Stock


@pytest.fixture
def setup(client, db_session):
    db_session.add(Stock(
        code="600519", name="贵州茅台", exchange="sh",
        listing_status="normally_listed", prev_close=100.0,
    ))
    db_session.add(Stock(
        code="600002", name="暂停上市", exchange="sh",
        listing_status="ipo_suspension", prev_close=50.0,
    ))
    db_session.add(Stock(
        code="000048", name="ST股", exchange="sz",
        listing_status="special_treatment", prev_close=10.0,
    ))
    db_session.add(Stock(
        code="300001", name="创业板", exchange="sz",
        listing_status="normally_listed", prev_close=20.0,
    ))
    db_session.add(Stock(
        code="688001", name="科创板", exchange="sh",
        listing_status="normally_listed", prev_close=50.0,
    ))
    db_session.add(Stock(
        code="999999", name="无前收", exchange="sh",
        listing_status="normally_listed", prev_close=None,
    ))
    db_session.flush()


def test_get_price_band_main(client, setup):
    resp = client.get("/api/stocks/600519/price-band")
    assert resp.status_code == 200
    data = resp.json()
    assert data["low"] == pytest.approx(90.0, abs=0.01)
    assert data["high"] == pytest.approx(110.0, abs=0.01)
    assert data["prev_close"] == pytest.approx(100.0, abs=0.01)
    assert data["board"] == "main"
    assert data["is_st"] is False
    assert data["is_suspended"] is False
    assert data["listing_status"] == "normally_listed"


def test_get_price_band_suspended(client, setup):
    resp = client.get("/api/stocks/600002/price-band")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_suspended"] is True
    assert data["listing_status"] == "ipo_suspension"


def test_get_price_band_st(client, setup):
    resp = client.get("/api/stocks/000048/price-band")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_st"] is True
    # ST gets ±5% even though code prefix would suggest main
    assert data["low"] == pytest.approx(9.5, abs=0.01)
    assert data["high"] == pytest.approx(10.5, abs=0.01)


def test_get_price_band_chinext(client, setup):
    resp = client.get("/api/stocks/300001/price-band")
    assert resp.status_code == 200
    data = resp.json()
    assert data["board"] == "chinext"
    # ±20%
    assert data["low"] == pytest.approx(16.0, abs=0.01)
    assert data["high"] == pytest.approx(24.0, abs=0.01)


def test_get_price_band_star(client, setup):
    resp = client.get("/api/stocks/688001/price-band")
    assert resp.status_code == 200
    data = resp.json()
    assert data["board"] == "star"
    assert data["low"] == pytest.approx(40.0, abs=0.01)
    assert data["high"] == pytest.approx(60.0, abs=0.01)


def test_get_price_band_no_prev_close(client, setup):
    """No prev_close + lazy fetch returns no data → low/high/prev_close null
    but board/ST still returned. Uses code 999999 (non-existent on Lixinger)
    so lazy fetch returns False."""
    resp = client.get("/api/stocks/999999/price-band")
    assert resp.status_code == 200
    data = resp.json()
    assert data["low"] is None
    assert data["high"] is None
    assert data["prev_close"] is None
    assert data["board"] == "main"
    assert data["is_st"] is False


def test_get_price_band_not_found(client):
    resp = client.get("/api/stocks/999999/price-band")
    assert resp.status_code == 404
