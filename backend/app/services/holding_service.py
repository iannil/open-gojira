"""Holding service — business logic for portfolio management."""

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
from app.core.exceptions import EntityNotFound, BusinessRuleViolation
from app.models.holding import Holding
from app.models.stock import Stock

logger = logging.getLogger(__name__)


def _sync_stop_profit_rules(db: Session) -> None:
    """Best-effort sync of [auto-holding] stop_profit AlertRule set.

    Lazy import keeps alert_service decoupled (it imports Holding model, not
    this service). Failures are swallowed: holding mutations must not roll
    back because of an alert-side issue.
    """
    try:
        from app.services.alert_service import sync_stop_profit_rules_from_holdings

        sync_stop_profit_rules_from_holdings(db)
    except Exception:
        logger.warning("stop_profit rule sync failed", exc_info=True)


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


def create_holding(db: Session, data: dict, force: bool = False) -> Holding:
    """Create a new holding. Verifies the stock exists and enforces the
    15% industry-concentration cap unless ``force`` is True.

    Raises HTTP 409 when the new buy would push the industry weight over
    ``MAX_INDUSTRY_WEIGHT`` — this is the durable gate behind the principle
    "单一行业仓位不超过 15%". Pass ``force=True`` to bypass (e.g. when the
    user has explicitly acknowledged the breach via pre-trade check).
    """
    stock = db.query(Stock).filter(Stock.code == data.get("stock_code")).first()
    if not stock:
        raise EntityNotFound("Stock", data.get("stock_code"))

    if not force:
        breach = _industry_breach_after_buy(
            db,
            new_industry=stock.industry,
            new_cost=float(data.get("buy_price", 0)) * float(data.get("quantity", 0)),
        )
        if breach is not None:
            raise BusinessRuleViolation(
                f"买入后{breach['industry']}行业仓位 {breach['weight_pct']:.1f}% "
                f"将超过 {MAX_INDUSTRY_WEIGHT}% 上限，请调整数量或换行业；"
                "如确需强制买入，请在请求中传 force=true"
            )

    holding = Holding(**data)
    db.add(holding)
    db.flush()
    db.refresh(holding)
    _sync_stop_profit_rules(db)
    from app.services import audit_log_service
    audit_log_service.write(
        db,
        entity_type="holding",
        entity_id=str(holding.id),
        event="created",
        actor="user",
        summary=f"买入 {stock.name or holding.stock_code} {holding.quantity} 股 @ {holding.buy_price}",
        stock_code=holding.stock_code,
        payload={
            "buy_price": holding.buy_price,
            "quantity": holding.quantity,
            "stop_profit_price": holding.stop_profit_price,
            "rationale": holding.trade_rationale,
        },
    )
    return holding


def _industry_breach_after_buy(
    db: Session,
    new_industry: Optional[str],
    new_cost: float,
) -> Optional[dict]:
    """Return breach info if adding ``new_cost`` to ``new_industry`` would
    push the industry past MAX_INDUSTRY_WEIGHT. Uses cost basis (not market
    value) for the new buy to avoid depending on a live price at create
    time. Existing positions use current_value when available, cost basis
    as fallback.

    F20 (2026-06-18) caveat: ``new_industry`` here is ``Stock.industry`` which
    currently stores Lixinger ``fsTableType`` values (5 categories:
    non_financial/bank/security/insurance/other_financial), NOT real申万 industry.
    This means 5530/5626 stocks share industry="non_financial" — the cap
    effectively treats the entire non-financial universe as one bucket, which
    is far coarser than the intent of MAX_INDUSTRY_WEIGHT. The cap still
    meaningfully limits financial-sector concentration, but is essentially a
    no-op within non-financial. Will be fixed when F20真实现 ships.
    """
    if not new_industry or new_cost <= 0:
        return None

    summary = get_portfolio_summary(db)
    # Skip the cap on an empty portfolio — the first position is necessarily
    # 100% by definition; the cap only meaningfully governs concentration in
    # a multi-position portfolio.
    if not summary["holdings"] or summary["total_value"] <= 0:
        return None

    base_value = summary["total_value"] + new_cost

    industry_value = new_cost
    for h in summary["holdings"]:
        if (h.get("stock_industry") or "未知行业") == new_industry:
            industry_value += h.get("current_value") or (h["buy_price"] * h["quantity"])

    weight_pct = industry_value / base_value * 100
    if weight_pct > MAX_INDUSTRY_WEIGHT:
        return {"industry": new_industry, "weight_pct": weight_pct}
    return None


def update_holding(db: Session, holding_id: int, data: dict) -> Optional[Holding]:
    """Partially update a holding. Only sets keys that are not None."""
    holding = get_holding(db, holding_id)
    if not holding:
        return None

    for key, value in data.items():
        if value is not None:
            setattr(holding, key, value)

    db.flush()
    db.refresh(holding)
    _sync_stop_profit_rules(db)
    return holding


def get_holding(db: Session, holding_id: int) -> Optional[Holding]:
    """Get a single holding by ID."""
    return db.query(Holding).filter(Holding.id == holding_id).first()


def list_holdings(db: Session, active_only: bool = False) -> list:
    """List all holdings, ordered by buy_date descending.
    If active_only, filter to holdings that have not been sold."""
    query = db.query(Holding).order_by(Holding.buy_date.desc())
    if active_only:
        query = query.filter(Holding.sell_date.is_(None))
    return query.all()


def delete_holding(db: Session, holding_id: int) -> bool:
    """Delete a holding by ID. Returns True if deleted, False if not found."""
    holding = get_holding(db, holding_id)
    if holding:
        db.delete(holding)
        db.flush()
        _sync_stop_profit_rules(db)
        return True
    return False


def sell_holding(
    db: Session,
    holding_id: int,
    sell_date: date,
    sell_price: float,
    sell_thesis: Optional[str] = None,
) -> Optional[Holding]:
    """Mark a holding as sold."""
    holding = get_holding(db, holding_id)
    if not holding:
        return None

    holding.sell_date = sell_date
    holding.sell_price = sell_price
    holding.sell_thesis = sell_thesis
    db.flush()
    _sync_stop_profit_rules(db)
    from app.services import audit_log_service
    pnl_pct = None
    if holding.buy_price and holding.buy_price > 0:
        pnl_pct = (sell_price - holding.buy_price) / holding.buy_price * 100.0
    audit_log_service.write(
        db,
        entity_type="holding",
        entity_id=str(holding.id),
        event="sold",
        actor="user",
        summary=f"卖出 {holding.stock_code} @ {sell_price}"
        + (f"（{pnl_pct:+.1f}%）" if pnl_pct is not None else ""),
        stock_code=holding.stock_code,
        payload={
            "sell_price": sell_price,
            "buy_price": holding.buy_price,
            "pnl_pct": pnl_pct,
            "thesis": sell_thesis,
        },
    )
    return holding


def _holding_to_dict(holding: Holding, db: Session, stocks_map: dict | None = None) -> dict:
    """Convert a Holding ORM object to a dict with stock info and calculated fields.

    Args:
        stocks_map: Optional pre-fetched mapping of stock_code -> Stock ORM object.
                    When provided, avoids individual queries for each holding (N+1 fix).
    """
    if stocks_map and holding.stock_code in stocks_map:
        stock = stocks_map[holding.stock_code]
    else:
        stock = db.query(Stock).filter(Stock.code == holding.stock_code).first()
    stock_name = stock.name if stock else None
    stock_industry = stock.industry if stock else None
    stock_tier = stock.tier if stock else None

    cost = holding.buy_price * holding.quantity
    current_value: Optional[float] = None
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None

    try:
        price = _get_cached_price(holding.stock_code)
        if price is not None:
            current_value = price * holding.quantity
            pnl = current_value - cost
            pnl_pct = (pnl / cost) * 100 if cost != 0 else None
    except Exception:
        logger.warning("Price lookup failed for %s", holding.stock_code, exc_info=True)

    # Annualized return — geometric, based on hold days. None if missing inputs.
    annualized_return_pct: Optional[float] = None
    if holding.buy_date and current_value is not None and cost > 0:
        days = (date.today() - holding.buy_date).days
        # Need enough time to avoid divide-by-zero / wild values from <30d holdings.
        if days >= 30:
            ratio = current_value / cost
            if ratio > 0:
                raw = (ratio ** (365.0 / days) - 1) * 100
                annualized_return_pct = max(-100.0, min(raw, 500.0))

    return {
        "id": holding.id,
        "stock_code": holding.stock_code,
        "stock_name": stock_name,
        "stock_industry": stock_industry,
        "stock_tier": stock_tier,
        "buy_date": str(holding.buy_date) if holding.buy_date else None,
        "buy_price": holding.buy_price,
        "quantity": holding.quantity,
        "sell_date": str(holding.sell_date) if holding.sell_date else None,
        "sell_price": holding.sell_price,
        "stop_profit_price": holding.stop_profit_price,
        "trade_rationale": holding.trade_rationale,
        "sell_thesis": holding.sell_thesis,
        "current_value": current_value,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "annualized_return_pct": annualized_return_pct,
        "weight_pct": None,
    }


def _get_or_init_settings(db: Session):
    """Fetch (or lazy-create) the singleton cashflow_goals row (now includes portfolio settings)."""
    from app.models.cashflow_goal import CashflowGoal
    s = db.query(CashflowGoal).filter(CashflowGoal.id == 1).first()
    if not s:
        s = CashflowGoal(id=1, cash_reserve=0.0, target_weighted_dyr=0.045)
        db.add(s)
        db.flush()
        db.refresh(s)
    return s


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

    # Subquery: latest date per stock_code
    latest = (
        db.query(
            ValuationSnapshot.stock_code,
            sa_func.max(ValuationSnapshot.date).label("max_date"),
        )
        .filter(ValuationSnapshot.stock_code.in_(stock_codes))
        .group_by(ValuationSnapshot.stock_code)
        .subquery()
    )
    # Join back to get the dividend_yield at that date
    rows = (
        db.query(ValuationSnapshot.stock_code, ValuationSnapshot.dividend_yield)
        .join(
            latest,
            (ValuationSnapshot.stock_code == latest.c.stock_code)
            & (ValuationSnapshot.date == latest.c.max_date),
        )
        .all()
    )
    return {
        code: dy for code, dy in rows if dy is not None
    }


def get_portfolio_summary(db: Session) -> dict:
    """Build a portfolio summary for all active (unsold) holdings."""
    holdings = list_holdings(db, active_only=True)

    # Batch-fetch all stocks to avoid N+1 queries
    stock_codes = [h.stock_code for h in holdings]
    stocks_map: dict[str, Stock] = {}
    if stock_codes:
        stocks_map = {s.code: s for s in db.query(Stock).filter(Stock.code.in_(stock_codes)).all()}

    holding_dicts: list[dict] = []
    for h in holdings:
        holding_dicts.append(_holding_to_dict(h, db, stocks_map=stocks_map))

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

    # Stop-profit alerts
    for h in holding_dicts:
        if (
            h.get("current_value") is not None
            and h.get("stop_profit_price")
            and h["stop_profit_price"] > 0
        ):
            current_price = h["current_value"] / h["quantity"] if h["quantity"] > 0 else 0
            if current_price >= h["stop_profit_price"]:
                pct = ((current_price - h["stop_profit_price"]) / h["stop_profit_price"]) * 100
                warnings.append(
                    f"{h['stock_code']} 现价 {current_price:.2f} 已达止盈价 {h['stop_profit_price']:.2f}（+{pct:.1f}%），考虑卖出"
                )

    # Cash reserve & weighted dividend yield (methodology: 4-5% target)
    settings = _get_or_init_settings(db)
    cash_reserve = float(settings.cash_reserve or 0.0)
    target_weighted_dyr = float(settings.target_weighted_dyr or 0.045)
    grand_total = total_value + cash_reserve  # equity + cash
    cash_ratio_pct = (cash_reserve / grand_total * 100) if grand_total > 0 else 0.0

    # Weighted DYR = Σ(holding_value × DYR) / grand_total
    # Cash treated as 0% yield, conservative.
    weighted_dyr_num = 0.0
    have_any_dyr = False
    dyr_map = _batch_latest_dyrs(db, [h["stock_code"] for h in holding_dicts])
    for h in holding_dicts:
        dyr = dyr_map.get(h["stock_code"])
        if dyr is None:
            continue
        # Fall back to cost basis when live price is unavailable — same
        # convention used by total_value above so cash_ratio is comparable.
        value = h["current_value"] if h["current_value"] is not None else h["buy_price"] * h["quantity"]
        have_any_dyr = True
        weighted_dyr_num += value * float(dyr)
    portfolio_weighted_dyr = (weighted_dyr_num / grand_total) if (have_any_dyr and grand_total > 0) else None

    if portfolio_weighted_dyr is not None and portfolio_weighted_dyr < target_weighted_dyr:
        warnings.append(
            f"组合加权股息率 {portfolio_weighted_dyr*100:.2f}% 低于目标 {target_weighted_dyr*100:.1f}%"
        )

    # Weighted annualized return (by current value), ignores holdings <30d
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
    """Group active holdings by Stock.security_theme and aggregate weight + value.

    Allows the user to see how the portfolio is split across the 4 安全主线
    (能源/粮食/金融/资源 + 科技/信息/民生 ad-hoc).
    """
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

    Ranks active holdings by performance and assigns traffic-light signals:
      - green:  strong performer (pnl_pct >= +15%)
      - yellow: neutral / moderate (-10% <= pnl_pct < +15%)
      - red:    weak performer (pnl_pct < -10%)

    Also checks industry concentration (15% threshold).
    """
    summary = get_portfolio_summary(db)
    holdings = summary["holdings"]

    if not holdings:
        return {
            "holdings": [],
            "industry_warnings": [],
            "summary": "暂无持仓",
        }

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

    parts: list[str] = []
    parts.append(f"持仓 {len(items)} 只：{green_count} 只强势、{red_count} 只弱势")
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
