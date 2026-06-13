"""Stock CRUD endpoints."""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from typing import Optional

from app.db.session import get_db
from app.models.stock import Stock
from app.schemas.kline import KlineResponse, ValuationBandsResponse, KlineSummaryResponse
from app.schemas.stocks_detail import ShareholdersNumRecord, ThesisTemplatesResponse
from app.schemas.stock import (
    MarginTradingRecord,
    NorthFlowRecord,
    PriceBandResponse,
    QiuScoreInput,
    ShareholderRecord,
    StockCreate,
    StockResponse,
    StockUpdate,
    SyncResult,
    UniverseItem,
    FullUniverseItem,
    FullUniverseResponse,
    UniverseCoverageStats,
    ThesisVariable,
)
from app.services.data_service import fetch_stock_info, stock_to_response
from app.services.kline_service import get_klines, get_valuation_bands
from app.services.lixinger_client import LixingerError
from app.services.stocks_sync_service import fetch_industry_constituents, sync_stocks_from_lixinger as run_stock_sync
from app.services.stocks_detail_service import (
    get_customers,
    get_majority_shareholders,
    get_margin_trading,
    get_north_flow,
    get_revenue_composition,
    get_shareholders_num,
    get_suppliers,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stocks", tags=["stocks"])


@router.get("/universe", response_model=list[UniverseItem])
def get_universe(db: Session = Depends(get_db)):
    """Aggregate view of all watched + held stocks with tier/theme/plan status."""
    from app.services.universe_service import build_universe_view
    return build_universe_view(db)


@router.get("/universe/full", response_model=FullUniverseResponse)
def get_full_universe(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    pe_pct_max: Optional[float] = None,
    pb_pct_max: Optional[float] = None,
    dyr_min: Optional[float] = None,
    pe_ttm_min: Optional[float] = None,
    pe_ttm_max: Optional[float] = None,
    pb_min: Optional[float] = None,
    pb_max: Optional[float] = None,
    industry: Optional[str] = None,
    keyword: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Paginated view of all A-shares with latest valuation."""
    from sqlalchemy import func as sa_func
    from app.models.valuation import ValuationSnapshot

    q = db.query(Stock).filter(Stock.delisted_at.is_(None))

    if keyword:
        escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        kw = f"%{escaped}%"
        q = q.filter(
            (Stock.code.like(kw, escape="\\")) | (Stock.name.like(kw, escape="\\"))
        )

    if industry:
        q = q.filter(Stock.industry == industry)

    total = q.count()

    stocks = q.order_by(Stock.code).offset((page - 1) * page_size).limit(page_size).all()
    codes = [s.code for s in stocks]

    # Latest valuation per stock in page
    val_sub = db.query(
        ValuationSnapshot.stock_code,
        sa_func.max(ValuationSnapshot.date).label("max_date"),
    ).filter(ValuationSnapshot.stock_code.in_(codes)).group_by(
        ValuationSnapshot.stock_code
    ).subquery()
    latest_vals = db.query(ValuationSnapshot).join(
        val_sub,
        (ValuationSnapshot.stock_code == val_sub.c.stock_code)
        & (ValuationSnapshot.date == val_sub.c.max_date),
    ).all()
    val_map = {v.stock_code: v for v in latest_vals}

    items = []
    for s in stocks:
        v = val_map.get(s.code)
        item = FullUniverseItem(
            code=s.code,
            name=s.name,
            industry=s.industry,
            latest_pe_pct=v.pe_percentile_10y if v else None,
            latest_pb_pct=v.pb_percentile_10y if v else None,
            latest_dyr=v.dividend_yield if v else None,
            latest_pe_ttm=v.pe_ttm if v else None,
            latest_pb=v.pb if v else None,
        )

        # Apply valuation filters
        if pe_pct_max is not None and (item.latest_pe_pct is None or item.latest_pe_pct > pe_pct_max):
            continue
        if pb_pct_max is not None and (item.latest_pb_pct is None or item.latest_pb_pct > pb_pct_max):
            continue
        if dyr_min is not None and (item.latest_dyr is None or item.latest_dyr < dyr_min):
            continue
        if pe_ttm_min is not None and (item.latest_pe_ttm is None or item.latest_pe_ttm < pe_ttm_min):
            continue
        if pe_ttm_max is not None and (item.latest_pe_ttm is None or item.latest_pe_ttm > pe_ttm_max):
            continue
        if pb_min is not None and (item.latest_pb is None or item.latest_pb < pb_min):
            continue
        if pb_max is not None and (item.latest_pb is None or item.latest_pb > pb_max):
            continue

        items.append(item)

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/universe/stats", response_model=UniverseCoverageStats)
def get_universe_stats(db: Session = Depends(get_db)):
    """Universe coverage statistics."""
    from sqlalchemy import func as sa_func
    from app.models.valuation import ValuationSnapshot
    from datetime import date as date_type

    total_stocks = db.query(Stock).filter(Stock.delisted_at.is_(None)).count()
    today = date_type.today()
    stocks_with_valuation = db.query(
        sa_func.count(sa_func.distinct(ValuationSnapshot.stock_code))
    ).filter(ValuationSnapshot.date == today).scalar() or 0

    return UniverseCoverageStats(
        total_stocks=total_stocks,
        valuation_coverage=stocks_with_valuation,
        coverage_pct=round(stocks_with_valuation / max(1, total_stocks) * 100, 1),
        mode="full_coverage" if total_stocks > 1000 else "manual",
    )


@router.get("/kline-summary", response_model=KlineSummaryResponse)
def api_kline_summary(db: Session = Depends(get_db)):
    """K-line sync summary for all watched/held stocks."""
    from sqlalchemy import func as sa_func
    from app.models.price_kline import PriceKline

    stocks = db.query(Stock).all()
    items = []
    for s in stocks:
        row = db.query(
            sa_func.count(PriceKline.id).label("count"),
            sa_func.min(PriceKline.date).label("earliest"),
            sa_func.max(PriceKline.date).label("latest"),
        ).filter(PriceKline.stock_code == s.code).first()
        items.append({
            "stock_code": s.code,
            "stock_name": s.name,
            "earliest_date": str(row.earliest) if row and row.earliest else None,
            "latest_date": str(row.latest) if row and row.latest else None,
            "total_bars": row.count if row else 0,
        })
    return {"items": items}


@router.post("", response_model=StockResponse, status_code=201)
def create_stock(payload: StockCreate, db: Session = Depends(get_db)):
    """Create a new stock. If auto_fetch is True, fetch name/industry from Lixinger."""
    existing = db.query(Stock).filter(Stock.code == payload.code).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Stock {payload.code} already exists")

    name = payload.name
    industry = None

    if payload.auto_fetch:
        info = fetch_stock_info(payload.code)
        if info:
            name = name or info.get("name") or payload.code
            industry = info.get("industry")
        else:
            name = name or payload.code
    else:
        name = name or payload.code

    stock = Stock(code=payload.code, name=name, industry=industry)
    db.add(stock)
    db.commit()
    db.refresh(stock)

    return stock_to_response(stock, db)


@router.get("", response_model=list[StockResponse])
def list_stocks(db: Session = Depends(get_db)):
    """List all stocks."""
    stocks = db.query(Stock).options(joinedload(Stock.valuations)).all()
    return [stock_to_response(s, db) for s in stocks]


@router.get("/{code}", response_model=StockResponse)
def get_stock(code: str, db: Session = Depends(get_db)):
    """Get stock details by code."""
    stock = db.query(Stock).options(
        joinedload(Stock.valuations)
    ).filter(Stock.code == code).first()
    if not stock:
        raise HTTPException(status_code=404, detail=f"Stock {code} not found")
    return stock_to_response(stock, db)


@router.get("/{code}/shareholders", response_model=list[ShareholderRecord])
def api_shareholders(code: str, days: int = 730, db: Session = Depends(get_db)):
    """Recent top-10 shareholder snapshots (default ~2 years)."""
    if not db.query(Stock).filter(Stock.code == code).first():
        raise HTTPException(status_code=404, detail=f"Stock {code} not found")
    return get_majority_shareholders(code, days=days)


@router.get("/{code}/north-flow", response_model=list[NorthFlowRecord])
def api_north_flow(code: str, days: int = Query(default=60, ge=1, le=730), db: Session = Depends(get_db)):
    """Northbound (互联互通) net-buy / holding for a single stock."""
    if not db.query(Stock).filter(Stock.code == code).first():
        raise HTTPException(status_code=404, detail=f"Stock {code} not found")
    return get_north_flow(code, days=days)


@router.get("/{code}/margin-trading", response_model=list[MarginTradingRecord])
def api_margin_trading(code: str, days: int = Query(default=60, ge=1, le=730), db: Session = Depends(get_db)):
    """Margin trading (融资融券) records for a single stock."""
    if not db.query(Stock).filter(Stock.code == code).first():
        raise HTTPException(status_code=404, detail=f"Stock {code} not found")
    return get_margin_trading(code, days=days)


@router.get("/{code}/kline", response_model=KlineResponse)
def api_kline(
    code: str,
    days: int = Query(default=365, ge=1, le=3650),
    freq: str = Query(default="day", pattern="^(day|week|month)$"),
    db: Session = Depends(get_db),
):
    """Daily K-line for a stock. Cached in DB; missing tail fetched from Lixinger."""
    from datetime import date as _date, timedelta as _td

    if not db.query(Stock).filter(Stock.code == code).first():
        raise HTTPException(status_code=404, detail=f"Stock {code} not found")

    end = _date.today()
    start = end - _td(days=max(1, days))
    rows = get_klines(db, code, start=start, end=end, freq=freq)
    return KlineResponse(
        stock_code=code,
        freq=freq,
        points=[
            {
                "date": r.date.isoformat(),
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume,
            }
            for r in rows
        ],
    )


@router.get("/{code}/valuation-bands", response_model=ValuationBandsResponse)
def api_valuation_bands(
    code: str,
    metric: str = Query(default="pe_ttm", pattern="^(pe_ttm|pb)$"),
    years: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
):
    """Historical close × PE/PB quantile bands (P10/P50/P90), the "遛狗模型" view."""
    if not db.query(Stock).filter(Stock.code == code).first():
        raise HTTPException(status_code=404, detail=f"Stock {code} not found")
    try:
        return get_valuation_bands(db, code, metric=metric, years=years)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{code}/shareholders-num", response_model=list[ShareholdersNumRecord])
def api_shareholders_num(code: str, years: int = Query(default=3, ge=1, le=10), db: Session = Depends(get_db)):
    """Shareholder-count history (筹码集中度)."""
    if not db.query(Stock).filter(Stock.code == code).first():
        raise HTTPException(status_code=404, detail=f"Stock {code} not found")
    return get_shareholders_num(code, years=years)


@router.get("/{code}/customers", response_model=list[dict])
def api_customers(code: str, years: int = 5, db: Session = Depends(get_db)):
    """Major customers history — used to inform 'qiu' upstream pricing-power."""
    if not db.query(Stock).filter(Stock.code == code).first():
        raise HTTPException(status_code=404, detail=f"Stock {code} not found")
    return get_customers(code, years=years)


@router.get("/{code}/suppliers", response_model=list[dict])
def api_suppliers(code: str, years: int = 5, db: Session = Depends(get_db)):
    """Major suppliers history — used to inform 'qiu' downstream pricing-power."""
    if not db.query(Stock).filter(Stock.code == code).first():
        raise HTTPException(status_code=404, detail=f"Stock {code} not found")
    return get_suppliers(code, years=years)


@router.get("/{code}/revenue-composition", response_model=list[dict])
def api_revenue_composition(code: str, years: int = 5, db: Session = Depends(get_db)):
    """Revenue composition by business segment for recent N years.

    Surfaces the empirical evidence for the "求" pricing-power scoring:
    a company with strong upstream pricing power typically shows a
    concentrated revenue base in one core segment.
    """
    if not db.query(Stock).filter(Stock.code == code).first():
        raise HTTPException(status_code=404, detail=f"Stock {code} not found")
    return get_revenue_composition(code, years=years)


@router.put("/{code}", response_model=StockResponse)
def update_stock(code: str, payload: StockUpdate, db: Session = Depends(get_db)):
    """Update stock fields."""
    stock = db.query(Stock).options(
        joinedload(Stock.valuations)
    ).filter(Stock.code == code).first()
    if not stock:
        raise HTTPException(status_code=404, detail=f"Stock {code} not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(stock, field, value)

    db.commit()
    db.refresh(stock)
    return stock_to_response(stock, db)


@router.put("/{code}/thesis-variables", response_model=StockResponse)
def update_thesis_variables(code: str, variables: list[ThesisVariable], db: Session = Depends(get_db)):
    """Update thesis variables for a stock."""
    stock = db.query(Stock).options(
        joinedload(Stock.valuations)
    ).filter(Stock.code == code).first()
    if not stock:
        raise HTTPException(status_code=404, detail=f"Stock {code} not found")

    # Convert list of ThesisVariable to list of dicts, then to JSON
    variables_list = [v.model_dump() for v in variables]
    stock.thesis_variables_json = json.dumps(variables_list, ensure_ascii=False)

    db.commit()
    db.refresh(stock)
    return stock_to_response(stock, db)


@router.put("/{code}/qiu-score", response_model=StockResponse)
def update_qiu_score(code: str, payload: QiuScoreInput, db: Session = Depends(get_db)):
    """Structured "求" scoring: upstream + downstream + government bargaining power."""
    stock = db.query(Stock).options(
        joinedload(Stock.valuations)
    ).filter(Stock.code == code).first()
    if not stock:
        raise HTTPException(status_code=404, detail=f"Stock {code} not found")

    score = payload.upstream_power + payload.downstream_power + payload.government_power
    stock.qiu_score = score
    stock.qiu_detail_json = json.dumps({
        "upstream_power": payload.upstream_power,
        "downstream_power": payload.downstream_power,
        "government_power": payload.government_power,
        "evidence": payload.evidence,
    }, ensure_ascii=False)
    db.commit()
    db.refresh(stock)
    return stock_to_response(stock, db)


@router.get("/{code}/thesis-templates", response_model=ThesisTemplatesResponse)
def get_thesis_templates(code: str, db: Session = Depends(get_db)):
    """Return thesis variable template for a stock's industry."""
    stock = db.query(Stock).filter(Stock.code == code).first()
    if not stock:
        raise HTTPException(status_code=404, detail=f"Stock {code} not found")
    from app.services.thesis_variable_sync_service import get_template_for_industry
    return {"industry": stock.industry, "templates": get_template_for_industry(stock.industry)}


@router.post("/sync", response_model=SyncResult)
def sync_stocks_from_lixinger(db: Session = Depends(get_db)):
    """Sync all A-share stocks from Lixinger into local database.

    Thin router wrapper — the actual two-phase sync lives in
    ``stocks_sync_service.sync_stocks_from_lixinger`` so it can be unit-tested
    without a FastAPI TestClient. See that function for the contract.
    """
    try:
        return run_stock_sync(db)
    except LixingerError:
        logger.exception("Stock sync aborted: Lixinger API failure")
        raise HTTPException(status_code=502, detail="Failed to fetch data from Lixinger")


@router.get("/{code}/bank-blindbox")
def api_get_bank_blindbox(code: str, db: Session = Depends(get_db)):
    """Bank blind-box analysis (dividend + region + OCF/NI matching)."""
    from app.services.bank_analyzer_service import analyze
    result = analyze(db, code)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Stock {code} not found")
    return result.to_dict()


@router.get("/{code}/price-band", response_model=PriceBandResponse)
def api_price_band(code: str, db: Session = Depends(get_db)):
    """Return 涨跌停 band + 板块 + ST/停牌状态 for UI price validation.

    If ``prev_close`` is missing, lazily fetches it from Lixinger K-line
    (single stock, no rate-limit risk) and re-tries. ``low`` / ``high``
    remain ``None`` only if Lixinger has no K-line data (e.g. IPO day).
    """
    from app.services.kline_service import update_prev_close_for_stock
    from app.services.price_validator_service import (
        NoPrevCloseError,
        detect_board,
        is_suspended,
        is_st_stock,
        price_band,
    )

    stock = db.query(Stock).filter(Stock.code == code).first()
    if not stock:
        raise HTTPException(status_code=404, detail=f"Stock {code} not found")
    try:
        low, high = price_band(stock)
    except NoPrevCloseError:
        # Lazy-fetch from Lixinger + retry once.
        try:
            if update_prev_close_for_stock(db, code):
                db.commit()
                db.refresh(stock)
                low, high = price_band(stock)
            else:
                return PriceBandResponse(
                    code=code,
                    low=None,
                    high=None,
                    prev_close=None,
                    board=detect_board(stock.exchange, stock.code),
                    is_st=is_st_stock(stock.listing_status),
                    is_suspended=is_suspended(stock.listing_status),
                    listing_status=stock.listing_status,
                )
        except NoPrevCloseError:
            return PriceBandResponse(
                code=code,
                low=None,
                high=None,
                prev_close=None,
                board=detect_board(stock.exchange, stock.code),
                is_st=is_st_stock(stock.listing_status),
                is_suspended=is_suspended(stock.listing_status),
                listing_status=stock.listing_status,
            )
        except Exception as e:
            # Lixinger failure shouldn't block trade entry — return null band.
            logging.getLogger(__name__).warning(
                "Lazy prev_close fetch failed for %s: %s", code, e,
            )
            return PriceBandResponse(
                code=code,
                low=None,
                high=None,
                prev_close=None,
                board=detect_board(stock.exchange, stock.code),
                is_st=is_st_stock(stock.listing_status),
                is_suspended=is_suspended(stock.listing_status),
                listing_status=stock.listing_status,
            )
    return PriceBandResponse(
        code=code,
        low=low,
        high=high,
        prev_close=stock.prev_close,
        board=detect_board(stock.exchange, stock.code),
        is_st=is_st_stock(stock.listing_status),
        is_suspended=is_suspended(stock.listing_status),
        listing_status=stock.listing_status,
    )
