"""position_service — derive holdings & P&L from the Trade ledger.

Event sourcing (decision Q2-A, 2026-06-26 paper-trading loop design):
the immutable ``trades`` table is the single source of truth for positions.
Current quantity, moving-weighted-average cost basis, realized P&L and
unrealized P&L are all *derived* here — no separate Holding state.

Trade conventions (see app/models/trade.py):
- ``quantity`` is signed: +N BUY, -N SELL, 0 DIVIDEND, +/-N CORP_ACTION.
- ``total_value``: BUY = notional + fees (cash out, positive);
  SELL = notional - fees (cash in, positive).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.models.trade import Trade

PriceLookup = Callable[[str], Optional[float]]


def _default_price_lookup(code: str) -> Optional[float]:
    """Latest price from the shared holding_service cache (network-backed)."""
    from app.services.holding_service import _get_cached_price

    return _get_cached_price(code)


@dataclass
class Position:
    stock_code: str
    quantity: int
    avg_cost: float
    cost_basis: float
    realized_pnl: float
    unrealized_pnl: float


def _fold_trades(trades: list[Trade]) -> Position | None:
    """Replay a single stock's trades (chronological) into a Position.

    Moving weighted average: each BUY adds its full ``total_value`` (fees
    included) to the book cost; each SELL realizes P&L against the running
    average and removes cost proportionally. ``unrealized_pnl`` is left 0 here
    and filled in by callers that have a current price (see _compute_unrealized).
    """
    if not trades:
        return None

    code = trades[0].stock_code
    qty = 0
    cost_basis = 0.0  # book cost of shares currently held
    realized = 0.0

    for t in trades:
        if t.side == "BUY":
            qty += t.quantity
            cost_basis += t.total_value
        elif t.side == "SELL":
            sold = -t.quantity  # quantity is negative for SELL
            avg = cost_basis / qty if qty else 0.0
            realized += t.total_value - avg * sold
            cost_basis -= avg * sold
            qty -= sold
        elif t.side == "CORP_ACTION":
            # Share count changes (送股/拆股) with no cash impact: quantity
            # shifts, book cost is untouched → average cost is diluted/concentrated.
            qty += t.quantity

    avg_cost = cost_basis / qty if qty else 0.0
    return Position(
        stock_code=code,
        quantity=qty,
        avg_cost=avg_cost,
        cost_basis=cost_basis,
        realized_pnl=realized,
        unrealized_pnl=0.0,
    )


def position_for(
    db: Session, code: str, price_lookup: PriceLookup | None = None
) -> Position | None:
    """Derive the current position for one stock from its trade history.

    Returns the folded Position even when fully closed (quantity 0) so that
    realized P&L on closed positions stays queryable. Returns None only when
    the stock has no trades at all. ``price_lookup`` supplies the current price
    for unrealized P&L (defaults to the holding_service price cache).
    """
    trades = (
        db.query(Trade)
        .filter(Trade.stock_code == code)
        .order_by(Trade.filled_at, Trade.id)
        .all()
    )
    if not trades:
        return None
    lookup = price_lookup or _default_price_lookup
    pos = _fold_trades(trades)
    pos.unrealized_pnl = _compute_unrealized(pos, lookup(code))
    return pos


def available_quantity(db: Session, code: str, at_date: date) -> int:
    """T+1 sellable quantity on ``at_date``: net held shares minus shares
    bought on the same date (today's buys are frozen by the exchange rule)."""
    pos = position_for(db, code, price_lookup=lambda _c: None)
    held = pos.quantity if pos else 0
    bought_today = (
        db.query(Trade)
        .filter(Trade.stock_code == code, Trade.side == "BUY")
        .all()
    )
    frozen = sum(t.quantity for t in bought_today if t.filled_at.date() == at_date)
    return max(0, held - frozen)


def current_positions(
    db: Session, price_lookup: PriceLookup | None = None
) -> list[Position]:
    """All *open* positions (quantity != 0), derived from the trade ledger.

    Folds every stock without a price first, then looks up the current price
    only for the open positions — closed positions never trigger a price fetch.
    """
    lookup = price_lookup or _default_price_lookup
    codes = [row[0] for row in db.query(Trade.stock_code).distinct().all()]
    open_positions = []
    for code in codes:
        trades = (
            db.query(Trade)
            .filter(Trade.stock_code == code)
            .order_by(Trade.filled_at, Trade.id)
            .all()
        )
        pos = _fold_trades(trades)  # no price yet
        if pos and pos.quantity != 0:
            pos.unrealized_pnl = _compute_unrealized(pos, lookup(code))
            open_positions.append(pos)
    return open_positions


def _compute_unrealized(pos: Position, current_price: float | None) -> float:
    if current_price is None or not pos.quantity:
        return 0.0
    return (current_price - pos.avg_cost) * pos.quantity
