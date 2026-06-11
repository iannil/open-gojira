"""Dividend tracking endpoints — CRUD and summary for dividend records."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.common import OkResponse, SyncDividendResponse
from app.schemas.dividend import (
    DividendRecordCreate,
    DividendRecordResponse,
    DividendRecordUpdate,
    DividendSummaryResponse,
)
from app.services.dividend_service import (
    _record_to_dict,
    create_dividend_record,
    delete_dividend_record,
    fetch_and_store_from_lixinger,
    get_dividend_record,
    get_dividend_summary,
    list_dividend_records,
    update_dividend_record,
)

router = APIRouter(prefix="/api/dividends", tags=["dividends"])


@router.post("/{code}/sync", response_model=SyncDividendResponse)
def api_sync_dividends_from_lixinger(
    code: str,
    years: int = Query(default=10, ge=1, le=10),
    db: Session = Depends(get_db),
):
    """Sync historical dividend records for a stock from Lixinger."""
    inserted = fetch_and_store_from_lixinger(db, code, years=years)
    return {"stock_code": code, "inserted": inserted}


@router.post("/", response_model=DividendRecordResponse, status_code=201)
def api_create_dividend(payload: DividendRecordCreate, db: Session = Depends(get_db)):
    """Create a new dividend record."""
    data = payload.model_dump()
    record = create_dividend_record(db, data)
    return DividendRecordResponse(**_record_to_dict(record, db))


@router.get("/", response_model=list[DividendRecordResponse])
def api_list_dividends(
    stock_code: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """List dividend records, optionally filtered by stock code."""
    records = list_dividend_records(db, stock_code=stock_code)
    return [DividendRecordResponse(**_record_to_dict(r, db)) for r in records]


@router.get("/summary", response_model=DividendSummaryResponse)
def api_dividend_summary(db: Session = Depends(get_db)):
    """Get aggregated dividend summary grouped by year and stock."""
    result = get_dividend_summary(db)
    return DividendSummaryResponse(**result)


@router.get("/{record_id}", response_model=DividendRecordResponse)
def api_get_dividend(record_id: int, db: Session = Depends(get_db)):
    """Get a single dividend record by ID."""
    record = get_dividend_record(db, record_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Dividend record {record_id} not found")
    return DividendRecordResponse(**_record_to_dict(record, db))


@router.put("/{record_id}", response_model=DividendRecordResponse)
def api_update_dividend(
    record_id: int, payload: DividendRecordUpdate, db: Session = Depends(get_db)
):
    """Update a dividend record."""
    data = payload.model_dump(exclude_unset=True)
    record = update_dividend_record(db, record_id, data)
    if not record:
        raise HTTPException(status_code=404, detail=f"Dividend record {record_id} not found")
    return DividendRecordResponse(**_record_to_dict(record, db))


@router.delete("/{record_id}", response_model=OkResponse)
def api_delete_dividend(record_id: int, db: Session = Depends(get_db)):
    """Delete a dividend record."""
    success = delete_dividend_record(db, record_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Dividend record {record_id} not found")
    return {"ok": True}
