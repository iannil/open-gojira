"""Stock context builder — assembles StockContext from DB data.

Reuses existing helper functions from plan_snapshot for valuation,
financial, and dividend data. Adds bank analyzer and price data.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy import desc, func as sql_func, select
from sqlalchemy.orm import Session

from app.models.financial import FinancialStatement
from app.models.price_kline import PriceKline
from app.models.stock import Stock
from app.models.valuation import ValuationSnapshot
from app.services.strategy_engine import StockContext

logger = logging.getLogger(__name__)


def _latest_valuation(db: Session, code: str) -> ValuationSnapshot | None:
    return db.execute(
        select(ValuationSnapshot)
        .where(ValuationSnapshot.stock_code == code)
        .order_by(desc(ValuationSnapshot.date))
        .limit(1)
    ).scalar_one_or_none()


def _ocf_to_ni(db: Session, code: str) -> float | None:
    rows = db.execute(
        select(FinancialStatement)
        .where(FinancialStatement.stock_code == code)
        .order_by(desc(FinancialStatement.report_date))
        .limit(12)
    ).scalars().all()
    if not rows:
        return None
    ocf = sum((r.operating_cash_flow or 0.0) for r in rows)
    ni = sum((r.net_profit or 0.0) for r in rows)
    if ni <= 0:
        return None
    return ocf / ni


def _price_and_52w_high(db: Session, code: str) -> tuple[float | None, float | None]:
    """Return (latest_close, 52-week high) for a stock."""
    one_year_ago = date.today() - timedelta(days=365)

    rows = db.execute(
        select(PriceKline)
        .where(
            PriceKline.stock_code == code,
            PriceKline.date >= one_year_ago,
        )
        .order_by(desc(PriceKline.date))
    ).scalars().all()

    if not rows:
        return None, None

    latest = rows[0].close
    high = max((r.high for r in rows if r.high is not None), default=None)
    return latest, high


def _bulk_latest_valuations(db: Session, codes: list[str]) -> dict[str, ValuationSnapshot]:
    """Bulk-fetch latest ValuationSnapshot for multiple stocks."""
    if not codes:
        return {}
    # Subquery: max date per stock
    sub = (
        select(
            ValuationSnapshot.stock_code,
            sql_func.max(ValuationSnapshot.date).label("max_date"),
        )
        .where(ValuationSnapshot.stock_code.in_(codes))
        .group_by(ValuationSnapshot.stock_code)
        .subquery()
    )
    rows = db.execute(
        select(ValuationSnapshot)
        .join(sub, (ValuationSnapshot.stock_code == sub.c.stock_code) & (ValuationSnapshot.date == sub.c.max_date))
    ).scalars().all()
    return {v.stock_code: v for v in rows}


def _bulk_price_and_52w_highs(db: Session, codes: list[str]) -> dict[str, tuple[float | None, float | None]]:
    """Bulk-fetch (latest_close, 52w_high) for multiple stocks."""
    if not codes:
        return {}
    one_year_ago = date.today() - timedelta(days=365)
    rows = db.execute(
        select(PriceKline)
        .where(PriceKline.stock_code.in_(codes), PriceKline.date >= one_year_ago)
        .order_by(PriceKline.stock_code, desc(PriceKline.date))
    ).scalars().all()

    # Group by stock code
    from collections import defaultdict
    by_code: dict[str, list] = defaultdict(list)
    for r in rows:
        by_code[r.stock_code].append(r)

    result = {}
    for code in codes:
        klines = by_code.get(code, [])
        if not klines:
            result[code] = (None, None)
        else:
            latest = klines[0].close
            high = max((k.high for k in klines if k.high is not None), default=None)
            result[code] = (latest, high)
    return result


def _bulk_ocf_to_ni(db: Session, codes: list[str]) -> dict[str, float | None]:
    """Bulk-fetch OCF/NI ratio for multiple stocks (latest 12 quarters each)."""
    if not codes:
        return {}
    rows = db.execute(
        select(FinancialStatement)
        .where(FinancialStatement.stock_code.in_(codes))
        .order_by(FinancialStatement.stock_code, desc(FinancialStatement.report_date))
    ).scalars().all()

    from collections import defaultdict
    by_code: dict[str, list] = defaultdict(list)
    for r in rows:
        by_code[r.stock_code].append(r)

    result = {}
    for code in codes:
        stmts = by_code.get(code, [])[:12]
        if not stmts:
            result[code] = None
        else:
            ocf = sum((r.operating_cash_flow or 0.0) for r in stmts)
            ni = sum((r.net_profit or 0.0) for r in stmts)
            result[code] = ocf / ni if ni > 0 else None
    return result


def build_context(db: Session, code: str) -> StockContext:
    """Build a StockContext for a single stock from DB data."""
    stock = db.get(Stock, code)
    if stock is None:
        return StockContext(code=code)

    val = _latest_valuation(db, code)
    price, high_52w = _price_and_52w_high(db, code)

    # Compute price drop from 52-week high
    price_drop_pct = None
    if price and high_52w and high_52w > 0:
        price_drop_pct = (high_52w - price) / high_52w

    # Dividend sustainability score
    div_sust = None
    try:
        from app.services.dividend_sustainability_service import compute_sustainability_score
        div_sust = compute_sustainability_score(db, code)
    except Exception:
        logger.warning("dividend_sustainability failed for %s", code, exc_info=True)

    # Bank blind box verdict
    bank_verdict = None
    if stock.industry == "银行":
        try:
            from app.services.bank_analyzer_service import analyze
            result = analyze(db, code)
            if result:
                bank_verdict = result.blind_box_verdict
        except Exception:
            logger.warning("bank_analyzer failed for %s", code, exc_info=True)

    # Market temperature
    market_temp = None
    try:
        from app.services.market_temperature_service import compute_temperature
        market_temp = compute_temperature(db)
    except Exception:
        logger.warning("market_temperature failed", exc_info=True)

    # OCF/NI
    ocf_ni = _ocf_to_ni(db, code)

    # G3: Forward DYR (预期股息率) — uses 3-year avg dividend / latest price
    forward_dyr = None
    try:
        from app.services.dividend_projector_service import compute_forward_dyr_for_stock
        forward_dyr = compute_forward_dyr_for_stock(db, code)
    except Exception:
        logger.warning("compute_forward_dyr_for_stock failed for %s", code, exc_info=True)

    # C1: effective power_tier — qiu_score 优先, fallback 到 pattern.power_tier_baseline
    power_tier: int | None = None
    if stock.qiu_score and stock.qiu_score > 0:
        power_tier = stock.qiu_score
    elif stock.business_pattern_id is not None:
        from app.models.business_pattern import BusinessPattern
        bp = db.get(BusinessPattern, stock.business_pattern_id)
        if bp is not None:
            power_tier = bp.power_tier_baseline

    return StockContext(
        code=code,
        name=stock.name,
        industry=stock.industry,
        security_theme=stock.security_theme,
        tier=stock.tier,
        qiu_score=stock.qiu_score if stock.qiu_score else None,
        hq_region=stock.hq_region,
        dyr=val.dividend_yield if val else None,
        forward_dyr=forward_dyr,
        pe_pct_10y=(val.pe_percentile_10y / 100.0 if val and val.pe_percentile_10y is not None else None),
        pb_pct_10y=(val.pb_percentile_10y / 100.0 if val and val.pb_percentile_10y is not None else None),
        dividend_sustainability=div_sust,
        ocf_to_ni=ocf_ni,
        price=price,
        price_52w_high=high_52w,
        price_drop_pct=price_drop_pct,
        bank_blind_box=bank_verdict,
        market_temperature=market_temp,
        has_mine=stock.has_mine,
        domestic_leader=stock.domestic_leader,
        power_tier=power_tier,
    )


def build_contexts_batch(db: Session, codes: list[str]) -> dict[str, StockContext]:
    """Build StockContext for multiple stocks using bulk queries.

    Uses 3 bulk DB queries instead of N×3 per-stock queries,
    reducing 50 stocks from 150 queries to ~6 queries (3 bulk + service calls).
    """
    if not codes:
        return {}

    # Bulk-fetch stocks
    stocks = db.execute(
        select(Stock).where(Stock.code.in_(codes))
    ).scalars().all()
    stock_map = {s.code: s for s in stocks}

    # 3 bulk queries instead of N×3
    val_map = _bulk_latest_valuations(db, codes)
    price_map = _bulk_price_and_52w_highs(db, codes)
    ocf_map = _bulk_ocf_to_ni(db, codes)

    result: dict[str, StockContext] = {}
    for code in codes:
        try:
            s = stock_map.get(code)
            v = val_map.get(code)
            price, high_52w = price_map.get(code, (None, None))

            price_drop_pct = None
            if price and high_52w and high_52w > 0:
                price_drop_pct = (high_52w - price) / high_52w

            # Service calls remain per-stock (hard to batch), but wrapped in try/except
            div_sust = None
            try:
                from app.services.dividend_sustainability_service import compute_sustainability_score
                div_sust = compute_sustainability_score(db, code)
            except Exception:
                logger.warning("dividend_sustainability failed for %s", code, exc_info=True)

            bank_verdict = None
            if s and s.industry == "银行":
                try:
                    from app.services.bank_analyzer_service import analyze
                    r = analyze(db, code)
                    if r:
                        bank_verdict = r.blind_box_verdict
                except Exception:
                    logger.warning("bank_analyzer failed for %s", code, exc_info=True)

            market_temp = None
            try:
                from app.services.market_temperature_service import compute_temperature
                market_temp = compute_temperature(db)
            except Exception:
                logger.warning("market_temperature failed", exc_info=True)

            result[code] = StockContext(
                code=code,
                name=s.name if s else "",
                industry=s.industry if s else None,
                security_theme=s.security_theme if s else None,
                tier=s.tier if s else None,
                qiu_score=s.qiu_score if s and s.qiu_score else None,
                hq_region=s.hq_region if s else None,
                dyr=v.dividend_yield if v else None,
                pe_pct_10y=(v.pe_percentile_10y / 100.0 if v and v.pe_percentile_10y is not None else None),
                pb_pct_10y=(v.pb_percentile_10y / 100.0 if v and v.pb_percentile_10y is not None else None),
                dividend_sustainability=div_sust,
                ocf_to_ni=ocf_map.get(code),
                price=price,
                price_52w_high=high_52w,
                price_drop_pct=price_drop_pct,
                bank_blind_box=bank_verdict,
                market_temperature=market_temp,
            )
        except Exception as e:
            logger.warning("Failed to build context for %s: %s", code, e)
            result[code] = StockContext(code=code)

    return result


def build_screening_contexts(db: Session, codes: list[str]) -> dict[str, StockContext]:
    """Build lightweight StockContext for full-universe strategy screening.

    Uses only 2 bulk DB queries (stocks + today's valuations) instead of
    per-stock queries. Only base-tier fields are populated:
    code, name, industry, security_theme, tier, qiu_score, dyr, pe_pct_10y, pb_pct_10y.

    Deep-tier fields (dividend_sustainability, ocf_to_ni, price, bank_blind_box, etc.)
    are left as None and should be filled via build_context() in a second pass.
    """
    if not codes:
        return {}

    # Bulk query stocks
    stocks = db.execute(
        select(Stock).where(Stock.code.in_(codes))
    ).scalars().all()
    stock_map = {s.code: s for s in stocks}

    # Bulk query today's valuations
    today = date.today()
    vals = db.execute(
        select(ValuationSnapshot)
        .where(
            ValuationSnapshot.stock_code.in_(codes),
            ValuationSnapshot.date == today,
        )
    ).scalars().all()
    val_map = {v.stock_code: v for v in vals}

    result: dict[str, StockContext] = {}
    for code in codes:
        s = stock_map.get(code)
        v = val_map.get(code)
        result[code] = StockContext(
            code=code,
            name=s.name if s else "",
            industry=s.industry if s else None,
            security_theme=s.security_theme if s else None,
            tier=s.tier if s else None,
            qiu_score=s.qiu_score if s and s.qiu_score else None,
            hq_region=s.hq_region if s else None,
            dyr=v.dividend_yield if v else None,
            pe_pct_10y=(v.pe_percentile_10y / 100.0 if v and v.pe_percentile_10y is not None else None),
            pb_pct_10y=(v.pb_percentile_10y / 100.0 if v and v.pb_percentile_10y is not None else None),
        )
    return result
