"""Holding view — derived from trades (single source of truth).

Holdings are NOT a primary table; they are an aggregation over trades.
This service computes:
- Current open positions (total_quantity > 0)
- avg_cost_basis (weighted by BUY total_value)
- available_quantity_at(t): T+1 — shares bought before today
- frozen_quantity_at(t): today's buys (not yet settled)

For S2.1, plan_runner will call available_quantity_at() before generating
SELL drafts to ensure we don't suggest selling un-settled shares.
"""
from datetime import datetime, time
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.trade import Trade


def _start_of_day(d: datetime) -> datetime:
    """Midnight of the same date (for < comparison)."""
    return datetime.combine(d.date(), time.min)


def get_holding_view(
    db: Session,
    as_of: Optional[datetime] = None,
) -> list[dict]:
    """Return current open positions aggregated from trades.

    Args:
        db: SQLAlchemy session.
        as_of: Optional cutoff; only trades filled_at <= as_of are counted.

    Returns:
        List of dicts with: stock_code, total_quantity, avg_cost_basis,
        first_buy_at, last_trade_at. Closed positions (total_quantity <= 0)
        are excluded.
    """
    # Filter out reversed trades
    base_filter = [
        Trade.reversed_by_trade_id.is_(None),
    ]
    if as_of:
        base_filter.append(Trade.filled_at <= as_of)

    # Aggregate per stock_code
    rows = db.execute(
        select(
            Trade.stock_code,
            func.sum(Trade.quantity).label("total_quantity"),
            func.min(Trade.filled_at).label("first_buy_at"),
            func.max(Trade.filled_at).label("last_trade_at"),
        )
        .where(*base_filter)
        .group_by(Trade.stock_code)
    ).all()

    # For avg_cost_basis, we need BUY trades only
    buy_costs = {}
    buy_qtys = {}
    for row in rows:
        stock_code = row.stock_code
        buy_q = (
            select(
                func.sum(Trade.total_value).label("cost"),
                func.sum(Trade.quantity).label("qty"),
            )
            .where(
                Trade.stock_code == stock_code,
                Trade.side == "BUY",
                Trade.reversed_by_trade_id.is_(None),
            )
        )
        if as_of:
            buy_q = buy_q.where(Trade.filled_at <= as_of)
        r = db.execute(buy_q).one()
        buy_costs[stock_code] = float(r.cost or 0)
        buy_qtys[stock_code] = int(r.qty or 0)

    result = []
    for row in rows:
        qty = int(row.total_quantity or 0)
        if qty <= 0:
            continue  # closed position
        buy_qty = buy_qtys.get(row.stock_code, 0)
        avg_cost = (buy_costs.get(row.stock_code, 0) / buy_qty) if buy_qty > 0 else 0.0
        result.append({
            "stock_code": row.stock_code,
            "total_quantity": qty,
            "avg_cost_basis": avg_cost,
            "first_buy_at": row.first_buy_at,
            "last_trade_at": row.last_trade_at,
        })
    return result


def available_quantity_at(
    db: Session,
    stock_code: str,
    moment: datetime,
) -> int:
    """T+1: shares available to sell at `moment`.

    = (buys before today) - (sells already executed before `moment`)

    T+1 rule applies to BUYS only: today's buys are frozen, not available.
    SELLs are facts — once executed they immediately reduce available
    (this matters when querying mid-day after a SELL has filled).
    """
    today_start = _start_of_day(moment)

    buys_before = db.execute(
        select(func.sum(Trade.quantity))
        .where(
            Trade.stock_code == stock_code,
            Trade.side == "BUY",
            Trade.filled_at < today_start,
            Trade.reversed_by_trade_id.is_(None),
        )
    ).scalar() or 0

    sells_before = db.execute(
        select(func.sum(Trade.quantity))  # SELL quantity is negative
        .where(
            Trade.stock_code == stock_code,
            Trade.side == "SELL",
            Trade.filled_at < moment,
            Trade.reversed_by_trade_id.is_(None),
        )
    ).scalar() or 0

    return int(buys_before) + int(sells_before)  # sells_before is negative


def frozen_quantity_at(
    db: Session,
    stock_code: str,
    moment: datetime,
) -> int:
    """T+1: shares bought today (frozen until next trading day)."""
    today_start = _start_of_day(moment)
    # Trades on the same date as moment
    # Note: filled_at is naive datetime; compare by date.
    today_end = datetime.combine(moment.date(), time.max)

    buys_today = db.execute(
        select(func.sum(Trade.quantity))
        .where(
            Trade.stock_code == stock_code,
            Trade.side == "BUY",
            Trade.filled_at >= today_start,
            Trade.filled_at <= today_end,
            Trade.reversed_by_trade_id.is_(None),
        )
    ).scalar() or 0

    sells_today = db.execute(
        select(func.sum(Trade.quantity))
        .where(
            Trade.stock_code == stock_code,
            Trade.side == "SELL",
            Trade.filled_at >= today_start,
            Trade.filled_at <= today_end,
            Trade.reversed_by_trade_id.is_(None),
        )
    ).scalar() or 0

    # Frozen = today's buys - today's sells (sells consume from available,
    # but for simplicity in frozen calc, we report net today's buys)
    return int(buys_today) + int(sells_today)
