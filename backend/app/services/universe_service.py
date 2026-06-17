"""Universe service — builds the aggregate universe view for the dashboard."""

import logging
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.models.candidate import Candidate
from app.models.holding import Holding
from app.models.stock import Stock
from app.models.valuation import ValuationSnapshot
from app.models.watchlist import WatchlistItem
from app.schemas.stock import UniverseItem
from app.services.holding_service import _get_cached_price

logger = logging.getLogger(__name__)


def build_universe_view(db: Session) -> list[UniverseItem]:
    """Build the universe aggregate view: held + watched stocks with weights, valuations, candidates."""
    # All stock codes from holdings + watchlist
    held_codes = {
        r[0] for r in db.query(Holding.stock_code).filter(Holding.sell_date.is_(None)).all()
    }
    watched_codes = {r[0] for r in db.query(WatchlistItem.stock_code).distinct().all()}
    all_codes = held_codes | watched_codes

    if not all_codes:
        return []

    stocks = db.query(Stock).filter(Stock.code.in_(all_codes)).all()
    stock_map = {s.code: s for s in stocks}

    # Active candidates
    candidate_rows = db.query(Candidate).filter(Candidate.status == "active").all()
    candidate_map: dict[str, int] = {}
    for c in candidate_rows:
        candidate_map[c.stock_code] = candidate_map.get(c.stock_code, 0) + 1

    # Latest valuation per stock (bulk)
    val_sub = db.query(
        ValuationSnapshot.stock_code,
        sa_func.max(ValuationSnapshot.date).label("max_date"),
    ).filter(ValuationSnapshot.stock_code.in_(all_codes)).group_by(
        ValuationSnapshot.stock_code
    ).subquery()
    latest_vals = db.query(ValuationSnapshot).join(
        val_sub,
        (ValuationSnapshot.stock_code == val_sub.c.stock_code)
        & (ValuationSnapshot.date == val_sub.c.max_date),
    ).all()
    val_map = {v.stock_code: v for v in latest_vals}

    # Weight calculation — use current market value (consistent with portfolio summary)
    all_holdings_list = db.query(Holding).filter(Holding.sell_date.is_(None)).all()
    holdings_by_code: dict[str, list] = {}
    for h in all_holdings_list:
        holdings_by_code.setdefault(h.stock_code, []).append(h)

    total_value = 0.0
    holding_values: dict[str, float] = {}
    for hcode, hs in holdings_by_code.items():
        price = _get_cached_price(hcode)
        val = sum(
            (price * h.quantity) if price is not None else (h.buy_price * h.quantity)
            for h in hs
        )
        holding_values[hcode] = val
        total_value += val
    total_value = total_value or 1.0

    result = []
    for code in sorted(all_codes):
        s = stock_map.get(code)
        if not s:
            continue
        cand_count = candidate_map.get(code, 0)
        v = val_map.get(code)
        is_held = code in held_codes
        weight = None
        if is_held:
            weight = holding_values.get(code, 0) / total_value * 100

        result.append(UniverseItem(
            code=code,
            name=s.name,
            tier=s.tier,
            in_circle=s.in_circle,
            security_theme=s.security_theme,
            industry=s.industry,
            qiu_score=s.qiu_score,
            has_plan=cand_count > 0,
            plan_status="active" if cand_count > 0 else None,
            candidate_count=cand_count,
            is_held=is_held,
            weight_pct=round(weight, 2) if weight else None,
            latest_pe_pct=v.pe_percentile_10y if v else None,
            latest_dyr=v.dividend_yield if v else None,
        ))
    return result
