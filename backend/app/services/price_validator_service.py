"""Price validator — A-share 涨跌停 / 停牌 / 板块识别.

Rules (S0.6 spike confirmed):
- 板块(由 exchange + code prefix 推断):
  - 主板 (600/601/603/605/000/001/002/003): ±10%
  - 创业板 (300/301): ±20%
  - 科创板 (688/689): ±20%
  - 北交所 (920xxx, exchange=bj): ±30%
- ST 状态(由 listing_status 推断,优先于板块规则):
  - special_treatment / delisting_risk_warning / delisting_transitional_period: ±5%
- 停牌(由 listing_status 推断):
  - delisting_transitional_period / ipo_suspension / issued_but_not_listed /
    issue_failure / unauthorized: 视为停牌,禁止交易
"""
from __future__ import annotations

from datetime import date

from fastapi import HTTPException

from app.models.stock import Stock


# --- 板块 / ST / 停牌 推断 ----------------------------------------------------

def detect_board(exchange: str | None, code: str) -> str:
    """Infer board from exchange + code prefix.

    Args:
        exchange: 'sh' / 'sz' / 'bj' from Stock.exchange
        code: stock code (e.g. '600519')

    Returns:
        'main' / 'chinext' / 'star' / 'bjse'
    """
    if exchange == "bj" or code.startswith("920"):
        return "bjse"
    if code.startswith("688") or code.startswith("689"):
        return "star"
    if code.startswith("300") or code.startswith("301"):
        return "chinext"
    return "main"  # default conservative


# ST 状态:listing_status 在这些值时算 ST(±5% 规则)
_ST_STATUSES = frozenset({
    "special_treatment",
    "delisting_risk_warning",
    "delisting_transitional_period",
})


def is_st_stock(listing_status: str | None) -> bool:
    """Check if stock is in ST/*ST/退市整理期 state (gets ±5% limit)."""
    return listing_status in _ST_STATUSES


# 停牌状态:这些 listing_status 视为不可交易
_SUSPENDED_STATUSES = frozenset({
    "delisting_transitional_period",  # 退市整理期(还能交易但极高风险,简化处理禁掉)
    "ipo_suspension",                  # 暂停上市
    "issued_but_not_listed",           # 已发行未上市
    "issue_failure",                   # 发行失败
    "unauthorized",                    # 未批准
})


def is_suspended(listing_status: str | None) -> bool:
    """Check if stock is suspended / not yet trading."""
    return listing_status in _SUSPENDED_STATUSES


# --- 价格区间 -----------------------------------------------------------------

_BOARD_LIMITS = {
    "main": 0.10,
    "chinext": 0.20,
    "star": 0.20,
    "bjse": 0.30,
}


def price_band(stock: Stock) -> tuple[float, float]:
    """Compute (lower_limit, upper_limit) for the stock.

    ST overrides board rule (±5% regardless of board).
    """
    if stock.prev_close is None or stock.prev_close <= 0:
        raise NoPrevCloseError(stock.code)

    if is_st_stock(stock.listing_status):
        limit = 0.05
    else:
        limit = _BOARD_LIMITS.get(
            detect_board(stock.exchange, stock.code),
            0.10,  # conservative default
        )
    return (stock.prev_close * (1 - limit), stock.prev_close * (1 + limit))


# --- 校验入口 -----------------------------------------------------------------

class StockSuspendedError(HTTPException):
    def __init__(self, code: str, status: str | None):
        super().__init__(
            status_code=400,
            detail=f"Stock {code} is suspended (listing_status={status})",
        )


class PriceOutOfBandError(HTTPException):
    def __init__(self, code: str, price: float, low: float, high: float):
        super().__init__(
            status_code=400,
            detail=(
                f"Price ¥{price:.2f} for {code} is out of band "
                f"[¥{low:.2f}, ¥{high:.2f}]"
            ),
        )


class NoPrevCloseError(HTTPException):
    def __init__(self, code: str):
        super().__init__(
            status_code=400,
            detail=f"Stock {code} has no prev_close — cannot compute price band",
        )


# Tolerance for float drift (e.g. 110.0000001 should still pass at limit 110.0)
_PRICE_TOLERANCE = 0.01


def assert_tradable(stock: Stock, price: float, filled_at: date) -> None:
    """Raise if stock cannot be traded at `price` on `filled_at`.

    Checks:
    1. Stock not suspended (via listing_status)
    2. Price within band [prev_close × (1-limit), prev_close × (1+limit)]

    Raises:
        StockSuspendedError
        PriceOutOfBandError
        NoPrevCloseError
    """
    if is_suspended(stock.listing_status):
        raise StockSuspendedError(stock.code, stock.listing_status)
    low, high = price_band(stock)
    if price < low - _PRICE_TOLERANCE or price > high + _PRICE_TOLERANCE:
        raise PriceOutOfBandError(stock.code, price, low, high)
