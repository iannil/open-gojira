"""Backtest simulator — order matching on historical prices.

Pure functions operating on PortfolioState (in-memory). The engine
(S4C.4) drives the day loop and calls these per signal.

Constraints enforced:
- T+1: today's buys can't be sold today (can_sell_today check)
- Lot size: BUY quantity rounded down to multiple of 100
- Price band: target_price must be within [kline.low, kline.high] —
  if outside, the order couldn't have filled that day (涨跌停)
- Slippage: BUY pays target × (1 + bps/10000), SELL receives target × (1 - bps/10000)
- Fees: commission + stamp_duty (sell only) + transfer_fee (both)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from app.models.broker_fee_config import BrokerFeeConfig
from app.services.fee_calculator_service import compute_fees


LOT_SIZE = 100
DEFAULT_SLIPPAGE_BPS = 10  # 0.1%


@dataclass
class Position:
    """A single stock holding.

    Supports both attribute access (`.quantity`) and dict-style access
    (``pos["quantity"]``) plus ``.get()`` so callers can mix idioms.
    """
    quantity: int
    avg_cost: float
    buy_date: Optional[date] = None  # earliest buy date for T+1 check

    def __getitem__(self, key: str) -> Any:
        try:
            return getattr(self, key)
        except AttributeError as exc:
            raise KeyError(key) from exc

    def __setitem__(self, key: str, value: Any) -> None:
        if not hasattr(self, key):
            raise KeyError(key)
        setattr(self, key, value)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default) if hasattr(self, key) else default


@dataclass
class PortfolioState:
    cash: float
    positions: dict[str, Position] = field(default_factory=dict)
    """code → Position (quantity / avg_cost / buy_date). Dict inputs at
    construction are auto-converted to Position in __post_init__."""
    realized_pnl: float = 0.0
    trades_log: list[dict] = field(default_factory=list)
    """Append-only log of fills for later analysis."""

    def __post_init__(self) -> None:
        # Normalize dict inputs (e.g. test fixtures) into Position instances
        # so both `.attr` and `["key"]` access work uniformly.
        converted: dict[str, Position] = {}
        for code, pos in self.positions.items():
            if isinstance(pos, Position):
                converted[code] = pos
            elif isinstance(pos, dict):
                converted[code] = Position(
                    quantity=int(pos.get("quantity", 0)),
                    avg_cost=float(pos.get("avg_cost", 0.0)),
                    buy_date=pos.get("buy_date"),
                )
            else:
                raise TypeError(
                    f"Position for {code} must be Position or dict, got {type(pos)!r}"
                )
        self.positions = converted


@dataclass
class FillResult:
    success: bool
    filled_quantity: int = 0
    filled_price: float = 0.0
    commission: float = 0.0
    stamp_duty: float = 0.0
    transfer_fee: float = 0.0
    total_value: float = 0.0
    reason: str = ""


def can_sell_today(portfolio: PortfolioState, stock_code: str, today: date) -> bool:
    """T+1 check: position must have been bought before today."""
    pos = portfolio.positions.get(stock_code)
    if not pos or pos.get("quantity", 0) <= 0:
        return False
    buy_date = pos.get("buy_date")
    if buy_date is None:
        return True  # legacy / unknown — allow
    return buy_date < today


def _in_band(target_price: float, kline: dict, tolerance: float = 0.01) -> bool:
    """Check if target_price could have filled today (within daily range)."""
    low = float(kline.get("low", 0))
    high = float(kline.get("high", 0))
    if low <= 0 or high <= 0:
        return True  # can't verify, allow
    return (low - tolerance) <= target_price <= (high + tolerance)


def simulate_buy(
    *,
    portfolio: PortfolioState,
    stock_code: str,
    target_price: float,
    quantity: int,
    kline: dict,
    broker_config: BrokerFeeConfig,
    slippage_bps: int = DEFAULT_SLIPPAGE_BPS,
    exchange: str | None = None,
    listing_status: str | None = None,
    today: Optional[date] = None,
) -> FillResult:
    # Lot rounding
    rounded_qty = (quantity // LOT_SIZE) * LOT_SIZE
    if rounded_qty <= 0:
        return FillResult(False, reason=f"Quantity {quantity} rounds to 0 (min lot {LOT_SIZE})")

    # Price band check
    if not _in_band(target_price, kline):
        return FillResult(
            False,
            reason=f"Price ¥{target_price} out of band "
                   f"[{kline.get('low')}, {kline.get('high')}] — likely 涨跌停 "
                   f"(limit up/down)",
        )

    # Apply slippage (BUY pays more)
    filled_price = target_price * (1 + slippage_bps / 10000)

    # Compute fees
    fees = compute_fees(
        side="BUY", price=filled_price, quantity=rounded_qty,
        broker_config=broker_config,
    )
    total_cost = fees.total_value("BUY")

    # Cash check
    if portfolio.cash < total_cost:
        return FillResult(
            False,
            reason=f"Insufficient cash: need ¥{total_cost:.2f}, have ¥{portfolio.cash:.2f}",
        )

    # Apply
    portfolio.cash -= total_cost
    pos = portfolio.positions.get(stock_code)
    if pos is not None:
        old_qty = pos.quantity
        new_qty = old_qty + rounded_qty
        # Weighted avg cost
        pos.avg_cost = (pos.avg_cost * old_qty + filled_price * rounded_qty) / new_qty
        pos.quantity = new_qty
        # buy_date stays as earliest
    else:
        portfolio.positions[stock_code] = Position(
            quantity=rounded_qty,
            avg_cost=filled_price,
            buy_date=today,
        )

    portfolio.trades_log.append({
        "side": "BUY", "code": stock_code, "qty": rounded_qty,
        "price": filled_price, "total": total_cost,
        "date": str(today) if today else None,
    })

    return FillResult(
        success=True, filled_quantity=rounded_qty, filled_price=filled_price,
        commission=fees.commission, stamp_duty=0.0,
        transfer_fee=fees.transfer_fee, total_value=total_cost,
    )


def simulate_sell(
    *,
    portfolio: PortfolioState,
    stock_code: str,
    target_price: float,
    quantity: int,
    kline: dict,
    broker_config: BrokerFeeConfig,
    slippage_bps: int = DEFAULT_SLIPPAGE_BPS,
    exchange: str | None = None,
    listing_status: str | None = None,
    today: Optional[date] = None,
) -> FillResult:
    pos = portfolio.positions.get(stock_code)
    if not pos or pos.get("quantity", 0) <= 0:
        return FillResult(False, reason=f"No position to sell for {stock_code}")

    # T+1
    if today and not can_sell_today(portfolio, stock_code, today):
        return FillResult(
            False,
            reason="T+1: position bought today, cannot sell until tomorrow",
        )

    # A 股规则: SELL can be < 1 lot when reducing an existing position
    # (e.g. sell 100 of a 250-share holding), but requesting more than held
    # is an over-sell and must be rejected (no silent capping).
    held = pos.get("quantity", 0)
    if quantity > held or quantity <= 0:
        return FillResult(
            False,
            reason=(
                f"Sell quantity {quantity} invalid or exceeds "
                f"position {held}"
            ),
        )
    sell_qty = quantity

    # Price band
    if not _in_band(target_price, kline):
        return FillResult(
            False,
            reason=f"Price ¥{target_price} out of band — likely 涨跌停",
        )

    # Slippage (SELL receives less)
    filled_price = target_price * (1 - slippage_bps / 10000)

    fees = compute_fees(
        side="SELL", price=filled_price, quantity=sell_qty,
        broker_config=broker_config,
    )
    total_proceeds = fees.total_value("SELL")  # positive

    # Apply
    portfolio.cash += total_proceeds
    avg_cost = pos.get("avg_cost", 0.0)
    realized = (
        (filled_price - avg_cost) * sell_qty
        - fees.commission - fees.stamp_duty - fees.transfer_fee
    )
    portfolio.realized_pnl += realized

    new_qty = held - sell_qty
    pos.quantity = new_qty
    if new_qty <= 0:
        del portfolio.positions[stock_code]

    portfolio.trades_log.append({
        "side": "SELL", "code": stock_code, "qty": sell_qty,
        "price": filled_price, "total": total_proceeds,
        "realized_pnl": realized,
        "date": str(today) if today else None,
    })

    return FillResult(
        success=True, filled_quantity=sell_qty, filled_price=filled_price,
        commission=fees.commission, stamp_duty=fees.stamp_duty,
        transfer_fee=fees.transfer_fee, total_value=total_proceeds,
    )


def apply_dividend(portfolio: PortfolioState, stock_code: str, per_share: float) -> None:
    """Cash dividend: add per_share × qty_held to cash."""
    pos = portfolio.positions.get(stock_code)
    if not pos or pos.get("quantity", 0) <= 0:
        return
    cash_in = per_share * pos.get("quantity", 0)
    portfolio.cash += cash_in
    portfolio.trades_log.append({
        "side": "DIVIDEND", "code": stock_code, "qty": 0,
        "price": 0, "total": -cash_in, "per_share": per_share,
    })


def apply_stock_dividend(
    portfolio: PortfolioState, stock_code: str, per_10_shares: float
) -> None:
    """Stock dividend (送股): add shares, dilute cost basis."""
    pos = portfolio.positions.get(stock_code)
    if not pos:
        return
    old_qty = pos.get("quantity", 0)
    new_shares = int(old_qty * per_10_shares / 10)
    if new_shares <= 0:
        return
    new_qty = old_qty + new_shares
    pos.avg_cost = pos.avg_cost * old_qty / new_qty  # cost basis dilutes
    pos.quantity = new_qty


def apply_capitalization(
    portfolio: PortfolioState, stock_code: str, per_10_shares: float
) -> None:
    """Capitalization (转增): same math as stock dividend."""
    apply_stock_dividend(portfolio, stock_code, per_10_shares)
