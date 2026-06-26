"""Holding service — portfolio analytics derived from the Trade ledger.

Q2-A (2026-06-26 paper-trading loop design): positions and P&L are derived
from the immutable ``trades`` table via :mod:`app.services.position_service`.
There is no Holding write path — entry/exit happens only by recording trades
(CSV import / Draft confirm / manual /trades). This module keeps the
portfolio *analytics* (summary / theme breakdown / rebalancing guide) and
sources them from derived positions instead of Holding rows.

Retired with the Holding write model (decision 2-A): per-holding
``stop_profit_price`` and its alerts — valuation-based take-profit now lives in
the sell_trigger (estimated fair value × 1.3, P2-1).
"""

import logging
import threading
import time
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.core.constants import (
    MAX_INDUSTRY_WEIGHT,
    MAX_POSITION_WEIGHT,
    REBALANCE_GREEN_THRESHOLD,
    REBALANCE_RED_THRESHOLD,
    REBALANCE_SHORT_TERM_DAYS,
)
from app.models.stock import Stock
from app.models.trade import Trade
from app.services import position_service

logger = logging.getLogger(__name__)


_price_cache: dict[str, tuple[float, float]] = {}
_price_cache_lock = threading.Lock()
_CACHE_TTL_SECONDS = 60.0


def _get_cached_price(code: str) -> Optional[float]:
    """Get price from cache if fresh enough, otherwise fetch and cache."""
    now = time.monotonic()
    with _price_cache_lock:
        if code in _price_cache:
            ts, price = _price_cache[code]
            if now - ts < _CACHE_TTL_SECONDS:
                return price

    try:
        from app.services.data_service import fetch_current_price

        price = fetch_current_price(code)
        if price is not None:
            with _price_cache_lock:
                _price_cache[code] = (now, price)
        return price
    except Exception:
        logger.warning("Failed to fetch price for %s", code, exc_info=True)
        return None


def _buy_dates(db: Session, codes: list[str]) -> dict[str, date]:
    """Earliest BUY filled_at (date) per stock — the position's open date."""
    if not codes:
        return {}
    rows = (
        db.query(Trade.stock_code, Trade.filled_at)
        .filter(Trade.stock_code.in_(codes), Trade.side == "BUY")
        .all()
    )
    out: dict[str, date] = {}
    for code, filled_at in rows:
        d = filled_at.date()
        if code not in out or d < out[code]:
            out[code] = d
    return out


def _position_to_dict(
    pos: position_service.Position,
    stock: Stock | None,
    buy_date: date | None,
    price: float | None,
) -> dict:
    """Shape a derived Position into the legacy holding dict (same keys as the
    old _holding_to_dict, sourced from trades)."""
    cost = pos.cost_basis
    current_value: Optional[float] = None
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    if price is not None:
        current_value = price * pos.quantity
        pnl = current_value - cost
        pnl_pct = (pnl / cost) * 100 if cost != 0 else None

    annualized_return_pct: Optional[float] = None
    if buy_date and current_value is not None and cost > 0:
        days = (date.today() - buy_date).days
        if days >= 30:
            ratio = current_value / cost
            if ratio > 0:
                raw = (ratio ** (365.0 / days) - 1) * 100
                annualized_return_pct = max(-100.0, min(raw, 500.0))

    return {
        "id": None,  # derived positions are keyed by stock_code, not an id
        "stock_code": pos.stock_code,
        "stock_name": stock.name if stock else None,
        "stock_industry": stock.industry if stock else None,
        "stock_tier": stock.tier if stock else None,
        "buy_date": str(buy_date) if buy_date else None,
        "buy_price": pos.avg_cost,
        "quantity": pos.quantity,
        "sell_date": None,
        "sell_price": None,
        "stop_profit_price": None,  # retired (decision 2-A) — see sell_trigger
        "trade_rationale": None,
        "sell_thesis": None,
        "current_value": current_value,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "annualized_return_pct": annualized_return_pct,
        "realized_pnl": pos.realized_pnl,
        "weight_pct": None,
    }


def list_holdings(db: Session, active_only: bool = False) -> list[dict]:
    """List current open positions (derived from the trade ledger).

    ``active_only`` is accepted for backward compatibility; derived positions
    are always the open set, so the flag is a no-op.
    """
    positions = position_service.current_positions(db, price_lookup=_get_cached_price)
    codes = [p.stock_code for p in positions]
    stocks_map = {
        s.code: s for s in db.query(Stock).filter(Stock.code.in_(codes)).all()
    } if codes else {}
    buy_dates = _buy_dates(db, codes)
    return [
        _position_to_dict(p, stocks_map.get(p.stock_code), buy_dates.get(p.stock_code),
                          _get_cached_price(p.stock_code))
        for p in positions
    ]


def _get_or_init_settings(db: Session):
    """v2 portfolio settings: cash_reserve from the CashBalance ledger
    (singleton id=1); target_weighted_dyr is a methodology constant (4.5%)."""
    from types import SimpleNamespace

    from app.models.cash_balance import CashBalance

    cb = db.query(CashBalance).filter(CashBalance.id == 1).first()
    cash_reserve = float(cb.balance) if cb and cb.balance is not None else 0.0
    return SimpleNamespace(cash_reserve=cash_reserve, target_weighted_dyr=0.045)


def _latest_dyr(db: Session, stock_code: str) -> float | None:
    """Most recent dividend_yield from ValuationSnapshot (Lixinger trailing-12m)."""
    from app.models.valuation import ValuationSnapshot
    snap = (
        db.query(ValuationSnapshot)
        .filter(ValuationSnapshot.stock_code == stock_code)
        .order_by(ValuationSnapshot.date.desc())
        .first()
    )
    return snap.dividend_yield if snap and snap.dividend_yield is not None else None


def _batch_latest_dyrs(db: Session, stock_codes: list[str]) -> dict[str, float]:
    """Batch-fetch latest DYR for multiple stocks in a single query."""
    if not stock_codes:
        return {}
    from sqlalchemy import func as sa_func
    from app.models.valuation import ValuationSnapshot

    latest = (
        db.query(
            ValuationSnapshot.stock_code,
            sa_func.max(ValuationSnapshot.date).label("max_date"),
        )
        .filter(ValuationSnapshot.stock_code.in_(stock_codes))
        .group_by(ValuationSnapshot.stock_code)
        .subquery()
    )
    rows = (
        db.query(ValuationSnapshot.stock_code, ValuationSnapshot.dividend_yield)
        .join(
            latest,
            (ValuationSnapshot.stock_code == latest.c.stock_code)
            & (ValuationSnapshot.date == latest.c.max_date),
        )
        .all()
    )
    return {code: dy for code, dy in rows if dy is not None}


def get_portfolio_summary(db: Session) -> dict:
    """Build a portfolio summary for all open positions (trade-derived)."""
    holding_dicts = list_holdings(db)

    total_cost = sum(h["buy_price"] * h["quantity"] for h in holding_dicts)
    has_any_price = any(h["current_value"] is not None for h in holding_dicts)
    total_value = sum(
        h["current_value"] if h["current_value"] is not None else h["buy_price"] * h["quantity"]
        for h in holding_dicts
    )
    if has_any_price:
        total_pnl = total_value - total_cost
        total_pnl_pct = (total_pnl / total_cost) * 100 if total_cost != 0 else 0.0
    else:
        total_pnl = None
        total_pnl_pct = None

    warnings: list[str] = []
    industry_weights: dict[str, float] = {}
    for h in holding_dicts:
        if total_value > 0 and h["current_value"] is not None:
            weight = (h["current_value"] / total_value) * 100
            h["weight_pct"] = weight
            if weight > MAX_POSITION_WEIGHT:
                warnings.append(
                    f"{h['stock_code']} weight {weight:.1f}% exceeds 20% threshold"
                )
            industry = h.get("stock_industry") or "未知行业"
            industry_weights[industry] = industry_weights.get(industry, 0.0) + weight

    for ind, w in industry_weights.items():
        if w > MAX_INDUSTRY_WEIGHT:
            warnings.append(f"{ind}行业仓位 {w:.1f}% 超过 {MAX_INDUSTRY_WEIGHT}% 限制")

    settings = _get_or_init_settings(db)
    cash_reserve = float(settings.cash_reserve or 0.0)
    target_weighted_dyr = float(settings.target_weighted_dyr or 0.045)
    grand_total = total_value + cash_reserve
    cash_ratio_pct = (cash_reserve / grand_total * 100) if grand_total > 0 else 0.0

    weighted_dyr_num = 0.0
    have_any_dyr = False
    dyr_map = _batch_latest_dyrs(db, [h["stock_code"] for h in holding_dicts])
    for h in holding_dicts:
        dyr = dyr_map.get(h["stock_code"])
        if dyr is None:
            continue
        value = h["current_value"] if h["current_value"] is not None else h["buy_price"] * h["quantity"]
        have_any_dyr = True
        weighted_dyr_num += value * float(dyr)
    portfolio_weighted_dyr = (weighted_dyr_num / grand_total) if (have_any_dyr and grand_total > 0) else None

    if portfolio_weighted_dyr is not None and portfolio_weighted_dyr < target_weighted_dyr:
        warnings.append(
            f"组合加权股息率 {portfolio_weighted_dyr*100:.2f}% 低于目标 {target_weighted_dyr*100:.1f}%"
        )

    weighted_ann_num = 0.0
    weighted_ann_denom = 0.0
    for h in holding_dicts:
        if h.get("annualized_return_pct") is None:
            continue
        value = h["current_value"] if h["current_value"] is not None else h["buy_price"] * h["quantity"]
        weighted_ann_num += value * h["annualized_return_pct"]
        weighted_ann_denom += value
    portfolio_annualized_pct = (
        weighted_ann_num / weighted_ann_denom if weighted_ann_denom > 0 else None
    )

    return {
        "total_cost": total_cost,
        "total_value": total_value,
        "total_pnl": total_pnl,
        "total_pnl_pct": total_pnl_pct,
        "position_count": len(holding_dicts),
        "holdings": holding_dicts,
        "warnings": warnings,
        "cash_reserve": cash_reserve,
        "cash_ratio_pct": cash_ratio_pct,
        "portfolio_weighted_dyr": portfolio_weighted_dyr,
        "target_weighted_dyr": target_weighted_dyr,
        "portfolio_annualized_pct": portfolio_annualized_pct,
    }


def get_theme_breakdown(db: Session) -> list[dict]:
    """Group open positions by Stock.security_theme and aggregate weight + value."""
    summary = get_portfolio_summary(db)
    holdings = summary["holdings"]
    total_value = float(summary["total_value"]) or 0.0
    if not holdings or total_value <= 0:
        return []

    stock_codes = [h["stock_code"] for h in holdings]
    themes_map: dict[str, str | None] = {}
    if stock_codes:
        for s in db.query(Stock).filter(Stock.code.in_(stock_codes)).all():
            themes_map[s.code] = s.security_theme

    buckets: dict[str, dict] = {}
    for h in holdings:
        value = h["current_value"] if h["current_value"] is not None else h["buy_price"] * h["quantity"]
        theme = themes_map.get(h["stock_code"]) or "未标注"
        bucket = buckets.setdefault(theme, {
            "theme": theme,
            "value": 0.0,
            "count": 0,
            "stock_codes": [],
        })
        bucket["value"] += value
        bucket["count"] += 1
        bucket["stock_codes"].append(h["stock_code"])

    result = []
    for theme, b in buckets.items():
        b["weight_pct"] = round((b["value"] / total_value) * 100, 2)
        b["value"] = round(b["value"], 2)
        result.append(b)
    result.sort(key=lambda x: x["weight_pct"], reverse=True)
    return result


def calculate_rebalancing_guide(db: Session) -> dict:
    """Build a rebalancing guide following the '人之道' principle.

    Ranks open positions by performance and assigns traffic-light signals:
      - green:  pnl_pct >= +15%
      - yellow: -10% <= pnl_pct < +15%
      - red:    pnl_pct < -10%
    Also checks industry concentration (15% threshold).
    """
    summary = get_portfolio_summary(db)
    holdings = summary["holdings"]

    if not holdings:
        return {"holdings": [], "industry_warnings": [], "summary": "暂无持仓"}

    today = date.today()
    industry_weights: dict[str, float] = {}

    items: list[dict] = []
    for h in holdings:
        pnl_pct = h.get("pnl_pct")
        weight = h.get("weight_pct") or 0.0
        buy_date_str = h.get("buy_date")
        hold_days = (today - date.fromisoformat(buy_date_str)).days if buy_date_str else None

        industry = h.get("stock_industry") or "未知行业"
        industry_weights[industry] = industry_weights.get(industry, 0.0) + weight

        if pnl_pct is None:
            signal = "yellow"
            suggestion = "无法获取最新价格，请手动评估"
        elif pnl_pct >= REBALANCE_GREEN_THRESHOLD:
            signal = "green"
            suggestion = "强势持仓，保持或适度集中"
        elif pnl_pct >= REBALANCE_RED_THRESHOLD:
            signal = "yellow"
            suggestion = "表现中性，继续持有观察"
        elif hold_days and hold_days < REBALANCE_SHORT_TERM_DAYS:
            signal = "yellow"
            suggestion = "短期波动，耐心等待"
        else:
            signal = "red"
            suggestion = "弱势持仓，考虑止损或换股"

        items.append({
            "stock_code": h["stock_code"],
            "stock_name": h.get("stock_name"),
            "stock_industry": industry,
            "pnl_pct": round(pnl_pct, 2) if pnl_pct is not None else None,
            "weight_pct": round(weight, 2),
            "hold_days": hold_days,
            "signal": signal,
            "suggestion": suggestion,
        })

    items.sort(key=lambda x: x["pnl_pct"] if x["pnl_pct"] is not None else float("-inf"), reverse=True)

    industry_warnings: list[str] = []
    for ind, w in industry_weights.items():
        if w > MAX_INDUSTRY_WEIGHT:
            industry_warnings.append(f"{ind}行业仓位 {w:.1f}% 超过 {MAX_INDUSTRY_WEIGHT}% 限制")

    green_count = sum(1 for i in items if i["signal"] == "green")
    red_count = sum(1 for i in items if i["signal"] == "red")

    parts: list[str] = [f"持仓 {len(items)} 只：{green_count} 只强势、{red_count} 只弱势"]
    if red_count > 0:
        parts.append("遵循'人之道'：优胜劣汰，考虑将弱势仓位转向强势标的")
    if industry_warnings:
        parts.append("注意行业集中度风险")
    summary_text = "。".join(parts)

    return {
        "holdings": items,
        "industry_warnings": industry_warnings,
        "summary": summary_text,
    }
