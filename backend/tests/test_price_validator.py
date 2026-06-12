"""Test price_validator_service — 涨跌停 / 停牌 / 板块识别."""
from datetime import date
import pytest

from app.models.stock import Stock
from app.services.price_validator_service import (
    detect_board, is_st_stock, price_band, assert_tradable,
    StockSuspendedError, PriceOutOfBandError, NoPrevCloseError,
)


# --- detect_board ---

@pytest.mark.parametrize("exchange,code,expected", [
    ("sh", "600519", "main"),    # 茅台 主板
    ("sh", "601318", "main"),    # 平安 主板
    ("sh", "688981", "star"),    # 中芯国际 科创板
    ("sz", "000001", "main"),    # 平安银行 主板
    ("sz", "300750", "chinext"), # 宁德时代 创业板
    ("sz", "301236", "chinext"), # 创业板(新规则)
    ("bj", "920126", "bjse"),    # 北交所
    ("bj", "830799", "bjse"),    # 北交所(老代码)
])
def test_detect_board(exchange, code, expected):
    assert detect_board(exchange, code) == expected


def test_detect_board_unknown_exchange():
    """Unknown exchange defaults to main (conservative ±10%)."""
    assert detect_board("unknown", "600519") == "main"


# --- is_st_stock ---

@pytest.mark.parametrize("status,expected", [
    ("normally_listed", False),
    ("special_treatment", True),       # ST
    ("delisting_risk_warning", True),  # *ST
    ("delisting_transitional_period", True),  # 退市整理期
    ("ipo_suspension", False),         # 暂停上市(不算 ST)
    (None, False),
])
def test_is_st_stock(status, expected):
    assert is_st_stock(status) == expected


# --- price_band ---

def test_price_band_main_normal():
    stock = Stock(code="600519", name="贵州茅台", exchange="sh",
                  listing_status="normally_listed", prev_close=100.0)
    low, high = price_band(stock)
    assert low == pytest.approx(90.0, abs=0.01)
    assert high == pytest.approx(110.0, abs=0.01)


def test_price_band_main_st():
    stock = Stock(code="600519", name="贵州茅台", exchange="sh",
                  listing_status="special_treatment", prev_close=100.0)
    low, high = price_band(stock)
    assert low == pytest.approx(95.0, abs=0.01)
    assert high == pytest.approx(105.0, abs=0.01)


def test_price_band_chinext():
    stock = Stock(code="300750", name="宁德时代", exchange="sz",
                  listing_status="normally_listed", prev_close=200.0)
    low, high = price_band(stock)
    assert low == pytest.approx(160.0, abs=0.01)
    assert high == pytest.approx(240.0, abs=0.01)


def test_price_band_star():
    stock = Stock(code="688981", name="中芯国际", exchange="sh",
                  listing_status="normally_listed", prev_close=50.0)
    low, high = price_band(stock)
    assert low == pytest.approx(40.0, abs=0.01)
    assert high == pytest.approx(60.0, abs=0.01)


def test_price_band_bjse():
    stock = Stock(code="920126", name="北证样本", exchange="bj",
                  listing_status="normally_listed", prev_close=10.0)
    low, high = price_band(stock)
    assert low == pytest.approx(7.0, abs=0.01)
    assert high == pytest.approx(13.0, abs=0.01)


def test_price_band_st_overrides_board():
    """ST rule (±5%) overrides board rule (±20% for chinext)."""
    stock = Stock(code="300750", name="宁德时代", exchange="sz",
                  listing_status="delisting_risk_warning",  # *ST
                  prev_close=200.0)
    low, high = price_band(stock)
    assert low == pytest.approx(190.0, abs=0.01)  # ±5% not ±20%
    assert high == pytest.approx(210.0, abs=0.01)


def test_price_band_no_prev_close_raises():
    stock = Stock(code="600519", name="贵州茅台", exchange="sh",
                  listing_status="normally_listed", prev_close=None)
    with pytest.raises(NoPrevCloseError):
        price_band(stock)


# --- assert_tradable ---

def _make_stock(code="600519", exchange="sh", status="normally_listed", prev_close=100.0):
    return Stock(code=code, name="测试股票", exchange=exchange,
                 listing_status=status, prev_close=prev_close)


def test_assert_tradable_normal_buy_in_band():
    stock = _make_stock(prev_close=100.0)
    # 应该 pass
    assert_tradable(stock, price=105.0, filled_at=date(2026, 6, 12))


def test_assert_tradable_at_upper_limit():
    stock = _make_stock(prev_close=100.0)
    assert_tradable(stock, price=110.0, filled_at=date(2026, 6, 12))  # 边界 OK


def test_assert_tradable_above_upper_limit():
    stock = _make_stock(prev_close=100.0)
    with pytest.raises(PriceOutOfBandError) as exc:
        assert_tradable(stock, price=115.0, filled_at=date(2026, 6, 12))
    assert "115.00" in str(exc.value)


def test_assert_tradable_below_lower_limit():
    stock = _make_stock(prev_close=100.0)
    with pytest.raises(PriceOutOfBandError):
        assert_tradable(stock, price=85.0, filled_at=date(2026, 6, 12))


def test_assert_tradable_suspended_raises():
    stock = _make_stock(status="delisting_transitional_period")  # 视为停牌
    with pytest.raises(StockSuspendedError):
        assert_tradable(stock, price=100.0, filled_at=date(2026, 6, 12))


def test_assert_tradable_ipo_suspension_raises():
    stock = _make_stock(status="ipo_suspension")
    with pytest.raises(StockSuspendedError):
        assert_tradable(stock, price=100.0, filled_at=date(2026, 6, 12))


def test_assert_tradable_tolerance():
    """Tiny float drift (0.01) should not trigger."""
    stock = _make_stock(prev_close=100.0)
    # upper limit = 110.0, 110.01 should be tolerated
    assert_tradable(stock, price=110.01, filled_at=date(2026, 6, 12))
