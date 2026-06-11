"""Dividend service — CRUD, summary aggregation, and Lixinger sync."""

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.dividend import DividendRecord
from app.models.holding import Holding
from app.models.stock import Stock
from app.services.lixinger_client import LixingerError, get_lixinger_client

logger = logging.getLogger(__name__)


def create_dividend_record(db: Session, data: dict) -> DividendRecord:
    """Create a new dividend record after verifying the stock exists.

    Args:
        db: SQLAlchemy session.
        data: Dict matching DividendRecord fields.

    Returns:
        The created DividendRecord ORM object.

    Raises:
        HTTPException 404: If the referenced stock does not exist.
    """
    stock = db.query(Stock).filter(Stock.code == data["stock_code"]).first()
    if not stock:
        raise HTTPException(status_code=404, detail=f"Stock {data['stock_code']} not found")

    record = DividendRecord(
        stock_code=data["stock_code"],
        ex_date=data["ex_date"],
        amount_per_share=data["amount_per_share"],
        quantity_held=data["quantity_held"],
        total_received=data["total_received"],
        reinvested=data.get("reinvested", False),
    )
    db.add(record)
    db.flush()
    db.refresh(record)
    return record


def update_dividend_record(
    db: Session, record_id: int, data: dict
) -> Optional[DividendRecord]:
    """Partially update a dividend record.

    Args:
        db: SQLAlchemy session.
        record_id: ID of the record to update.
        data: Dict with fields to update (only non-None values are applied).

    Returns:
        The updated DividendRecord, or None if not found.
    """
    record = db.query(DividendRecord).filter(DividendRecord.id == record_id).first()
    if not record:
        return None

    for field, value in data.items():
        if value is not None:
            setattr(record, field, value)

    db.flush()
    db.refresh(record)
    return record


def get_dividend_record(db: Session, record_id: int) -> Optional[DividendRecord]:
    """Get a single dividend record by ID.

    Args:
        db: SQLAlchemy session.
        record_id: ID of the record.

    Returns:
        The DividendRecord, or None if not found.
    """
    return db.query(DividendRecord).filter(DividendRecord.id == record_id).first()


def list_dividend_records(
    db: Session, stock_code: Optional[str] = None
) -> list[DividendRecord]:
    """List dividend records ordered by ex_date descending.

    Args:
        db: SQLAlchemy session.
        stock_code: Optional filter by stock code.

    Returns:
        List of DividendRecord objects.
    """
    query = db.query(DividendRecord).order_by(DividendRecord.ex_date.desc())
    if stock_code:
        query = query.filter(DividendRecord.stock_code == stock_code)
    return query.all()


def delete_dividend_record(db: Session, record_id: int) -> bool:
    """Delete a dividend record by ID.

    Args:
        db: SQLAlchemy session.
        record_id: ID of the record to delete.

    Returns:
        True if deleted, False if not found.
    """
    record = db.query(DividendRecord).filter(DividendRecord.id == record_id).first()
    if not record:
        return False
    db.delete(record)
    db.flush()
    return True


def _record_to_dict(record: DividendRecord, db: Session) -> dict:
    """Convert a DividendRecord ORM object to a plain dict with stock_name lookup.

    Args:
        record: DividendRecord ORM object.
        db: SQLAlchemy session for stock name lookup.

    Returns:
        Dict suitable for constructing DividendRecordResponse.
    """
    stock = db.query(Stock).filter(Stock.code == record.stock_code).first()
    stock_name = stock.name if stock else None

    return {
        "id": record.id,
        "stock_code": record.stock_code,
        "stock_name": stock_name,
        "ex_date": str(record.ex_date) if record.ex_date else None,
        "amount_per_share": record.amount_per_share,
        "quantity_held": record.quantity_held,
        "total_received": record.total_received,
        "reinvested": record.reinvested,
        "created_at": str(record.created_at) if record.created_at else None,
    }


def _parse_lx_date(value) -> Optional[date]:
    if not value:
        return None
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            try:
                return date.fromisoformat(value[:10])
            except ValueError:
                return None
    return None


def fetch_and_store_from_lixinger(db: Session, stock_code: str, years: int = 10) -> int:
    """Pull historical dividend records from Lixinger and upsert them.

    Historical records (no associated user holding) are stored with
    quantity_held=0 and total_received=0 so they can drive alerts and analytics
    without conflating with user-personal dividend rows.

    Returns the number of new records inserted.
    """
    stock = db.query(Stock).filter(Stock.code == stock_code).first()
    if not stock:
        raise HTTPException(status_code=404, detail=f"Stock {stock_code} not found")

    start = (date.today() - timedelta(days=int(365.25 * years))).isoformat()
    client = get_lixinger_client()
    try:
        rows = client.get_dividend(stock_code=stock_code, start_date=start)
    except LixingerError:
        logger.warning("Failed to fetch dividends for %s", stock_code, exc_info=True)
        return 0

    existing_dates: set[date] = {
        r.ex_date
        for r in db.query(DividendRecord.ex_date)
        .filter(
            DividendRecord.stock_code == stock_code,
            DividendRecord.quantity_held == 0,
        )
        .all()
        if r.ex_date
    }

    inserted = 0
    for row in rows:
        ex_date = _parse_lx_date(row.get("exDate")) or _parse_lx_date(row.get("date"))
        if not ex_date or ex_date in existing_dates:
            continue
        amount_per_share = row.get("dividend")
        if amount_per_share is None:
            continue
        db.add(DividendRecord(
            stock_code=stock_code,
            ex_date=ex_date,
            amount_per_share=float(amount_per_share),
            quantity_held=0,
            total_received=0.0,
            reinvested=False,
        ))
        existing_dates.add(ex_date)
        inserted += 1

    if inserted:
        db.commit()
    return inserted


def get_dividend_summary(db: Session) -> dict:
    """Compute aggregated dividend summary across all records.

    Groups dividends by year and by stock, and calculates annual yield
    per stock based on active holdings.

    Args:
        db: SQLAlchemy session.

    Returns:
        Dict with total_cumulative, by_year (list of DividendYearSummary),
        and by_stock (list of DividendStockSummary).
    """
    records = db.query(DividendRecord).all()

    if not records:
        return {
            "total_cumulative": 0.0,
            "by_year": [],
            "by_stock": [],
        }

    # Group by year
    year_totals: dict[int, float] = defaultdict(float)
    year_counts: dict[int, int] = defaultdict(int)
    for r in records:
        year = r.ex_date.year
        year_totals[year] += r.total_received
        year_counts[year] += 1

    by_year = [
        {"year": year, "total_received": round(year_totals[year], 2), "count": year_counts[year]}
        for year in sorted(year_totals.keys())
    ]

    # Group by stock
    stock_totals: dict[str, float] = defaultdict(float)
    stock_counts: dict[str, int] = defaultdict(int)
    for r in records:
        stock_totals[r.stock_code] += r.total_received
        stock_counts[r.stock_code] += 1

    by_stock = []
    twelve_months_ago = date.today() - timedelta(days=365)
    for code in sorted(stock_totals.keys()):
        stock = db.query(Stock).filter(Stock.code == code).first()
        stock_name = stock.name if stock else None

        # Calculate annual yield from active holdings using trailing 12-month dividends
        annual_yield = None
        active_holdings = (
            db.query(Holding)
            .filter(Holding.stock_code == code, Holding.sell_date.is_(None))
            .all()
        )
        if active_holdings:
            total_cost = sum(h.buy_price * h.quantity for h in active_holdings)
            total_qty = sum(h.quantity for h in active_holdings)
            if total_cost > 0 and total_qty > 0:
                trailing_dividends = sum(
                    r.total_received for r in records
                    if r.stock_code == code and r.ex_date and r.ex_date >= twelve_months_ago
                )
                avg_buy_price = total_cost / total_qty
                annual_yield = round(
                    (trailing_dividends / (avg_buy_price * total_qty)) * 100, 2
                )

        by_stock.append({
            "stock_code": code,
            "stock_name": stock_name,
            "total_received": round(stock_totals[code], 2),
            "count": stock_counts[code],
            "annual_yield": annual_yield,
        })

    total_cumulative = round(sum(r.total_received for r in records), 2)

    return {
        "total_cumulative": total_cumulative,
        "by_year": by_year,
        "by_stock": by_stock,
    }
