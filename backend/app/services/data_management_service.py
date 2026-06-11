"""Data management service — stock pool, data status, cleanup, sync delegation."""

import logging

from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.models.dividend import DividendRecord
from app.models.financial import FinancialStatement
from app.models.price_kline import PriceKline
from app.models.stock import Stock
from app.models.valuation import ValuationSnapshot
from app.models.watchlist import WatchlistItem

logger = logging.getLogger(__name__)


def get_watched_stock_codes(db: Session) -> set[str]:
    """Get all watched + held stock codes."""
    from app.models.holding import Holding
    held = {r[0] for r in db.query(Holding.stock_code).filter(Holding.sell_date.is_(None)).all()}
    watched = {r[0] for r in db.query(WatchlistItem.stock_code).distinct().all()}
    return held | watched


def get_all_active_stock_codes(db: Session) -> list[str]:
    """Get all non-delisted stock codes from the master list."""
    return [
        r[0] for r in db.query(Stock.code)
        .filter(Stock.delisted_at.is_(None))
        .all()
    ]


def list_stock_pool(db: Session) -> list[dict]:
    """List all stocks in the pool with data completeness info."""
    all_codes = get_watched_stock_codes(db)
    if not all_codes:
        return []

    stocks = db.query(Stock).filter(Stock.code.in_(all_codes)).all()
    stock_map = {s.code: s for s in stocks}

    # Batch query completeness
    val_codes = {r[0] for r in db.query(ValuationSnapshot.stock_code).filter(
        ValuationSnapshot.stock_code.in_(all_codes)
    ).distinct().all()}

    fin_codes = {r[0] for r in db.query(FinancialStatement.stock_code).filter(
        FinancialStatement.stock_code.in_(all_codes)
    ).distinct().all()}

    kline_codes = {r[0] for r in db.query(PriceKline.stock_code).filter(
        PriceKline.stock_code.in_(all_codes)
    ).distinct().all()}

    div_codes = {r[0] for r in db.query(DividendRecord.stock_code).filter(
        DividendRecord.stock_code.in_(all_codes)
    ).distinct().all()}

    # Watchlist added_at
    added_at_map: dict[str, str | None] = {}
    items = db.query(WatchlistItem).filter(WatchlistItem.stock_code.in_(all_codes)).all()
    for item in items:
        if item.stock_code not in added_at_map or (item.added_at and added_at_map.get(item.stock_code) is None):
            added_at_map[item.stock_code] = str(item.added_at) if item.added_at else None

    result = []
    for code in sorted(all_codes):
        s = stock_map.get(code)
        if not s:
            continue
        result.append({
            "code": code,
            "name": s.name,
            "industry": s.industry,
            "tier": s.tier,
            "security_theme": s.security_theme,
            "added_at": added_at_map.get(code),
            "data_completeness": {
                "has_valuation": code in val_codes,
                "has_financial": code in fin_codes,
                "has_kline": code in kline_codes,
                "has_dividend": code in div_codes,
            },
        })
    return result


def search_stocks(db: Session, keyword: str) -> list[dict]:
    """Search stocks by code or name."""
    if not keyword or len(keyword.strip()) < 1:
        return []
    kw = keyword.strip().replace("%", "\\%").replace("_", "\\_")
    query = db.query(Stock).filter(
        (Stock.code.ilike(f"%{kw}%", escape="\\")) | (Stock.name.ilike(f"%{kw}%", escape="\\"))
    ).limit(20)
    return [
        {
            "code": s.code,
            "name": s.name,
            "industry": s.industry,
            "listed_date": str(s.listed_date) if s.listed_date else None,
        }
        for s in query.all()
    ]


def add_to_pool(db: Session, stock_codes: list[str]) -> int:
    """Add stocks to the default watchlist group."""
    from app.services import watchlist_service as svc
    group = svc.get_or_create_default_group(db)
    return svc.bulk_add_items(db, group.id, stock_codes)


def remove_from_pool(db: Session, stock_codes: list[str]) -> int:
    """Remove stocks from all watchlist groups."""
    items = db.query(WatchlistItem).filter(
        WatchlistItem.stock_code.in_(stock_codes)
    ).all()
    count = len(items)
    for item in items:
        db.delete(item)
    db.flush()
    return count


def get_data_status(db: Session) -> dict:
    """Get aggregated data status for all data types."""
    watched_codes = get_watched_stock_codes(db)
    all_codes = watched_codes if watched_codes else set()

    def _status(model, date_col, code_filter=False) -> dict:
        q = db.query(
            sa_func.count(model.id).label("total"),
            sa_func.count(sa_func.distinct(model.stock_code)).label("stocks"),
            sa_func.max(date_col).label("latest"),
            sa_func.min(date_col).label("earliest"),
        )
        if code_filter and all_codes:
            q = q.filter(model.stock_code.in_(all_codes))
        row = q.first()
        return {
            "total_records": row.total or 0,
            "stock_count": row.stocks or 0,
            "latest_date": str(row.latest) if row.latest else None,
            "earliest_date": str(row.earliest) if row.earliest else None,
        }

    return {
        "valuations": _status(ValuationSnapshot, ValuationSnapshot.date, True),
        "financials": _status(FinancialStatement, FinancialStatement.report_date, True),
        "klines": _status(PriceKline, PriceKline.date, True),
        "dividends": _status(DividendRecord, DividendRecord.ex_date, True),
    }


def trigger_sync(db: Session, data_type: str, stock_codes: list[str] | None = None, years: int = 5) -> dict:
    """Trigger sync via Pipeline system. Delegates to PipelineManager."""
    from app.services.pipelines.manager import PipelineManager
    mgr = PipelineManager(db)
    return mgr.start(
        pipeline_type=data_type,
        stock_codes=stock_codes,
        years=years,
    )


def get_sync_status(db: Session, task_id: str) -> dict | None:
    """Get sync status. Looks up PipelineRun by ID."""
    from app.services.pipelines.manager import PipelineManager
    mgr = PipelineManager(db)
    return mgr.get_run(task_id)


def preview_cleanup(db: Session, data_type: str, before_date: str | None = None, after_date: str | None = None, stock_codes: list[str] | None = None) -> dict:
    """Preview how many records would be deleted."""
    model_map = {
        "valuations": (ValuationSnapshot, ValuationSnapshot.date),
        "financials": (FinancialStatement, FinancialStatement.report_date),
        "klines": (PriceKline, PriceKline.date),
        "dividends": (DividendRecord, DividendRecord.ex_date),
    }
    if data_type not in model_map:
        raise ValueError(f"Unknown data type: {data_type}")

    model, date_col = model_map[data_type]
    q = db.query(sa_func.count(model.id))

    if stock_codes:
        q = q.filter(model.stock_code.in_(stock_codes))
    if before_date:
        q = q.filter(date_col < before_date)
    if after_date:
        q = q.filter(date_col > after_date)

    count = q.scalar() or 0
    return {
        "data_type": data_type,
        "record_count": count,
    }


def execute_cleanup(db: Session, data_type: str, before_date: str | None = None, after_date: str | None = None, stock_codes: list[str] | None = None) -> dict:
    """Delete records by criteria."""
    model_map = {
        "valuations": (ValuationSnapshot, ValuationSnapshot.date),
        "financials": (FinancialStatement, FinancialStatement.report_date),
        "klines": (PriceKline, PriceKline.date),
        "dividends": (DividendRecord, DividendRecord.ex_date),
    }
    if data_type not in model_map:
        raise ValueError(f"Unknown data type: {data_type}")

    model, date_col = model_map[data_type]
    q = db.query(model)

    if stock_codes:
        q = q.filter(model.stock_code.in_(stock_codes))
    if before_date:
        q = q.filter(date_col < before_date)
    if after_date:
        q = q.filter(date_col > after_date)

    count = q.delete(synchronize_session="fetch")
    return {
        "data_type": data_type,
        "deleted_count": count,
    }