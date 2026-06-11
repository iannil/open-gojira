"""Valuation tools endpoints — percentile, snapshot, sustainability, dashboard."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.valuation import ValuationSnapshot
from app.schemas.valuation import (  # noqa: I001
    ForwardDyrResponse,
    DashboardResponse,
    PercentileResponse,
    SustainabilityResponse,
    ValuationSnapshotResponse,
)
from app.services.data_service import fetch_pe_pb_history
from app.services.valuation_service import (
    calculate_forward_dyr,
    calculate_percentiles,
    check_dividend_sustainability,
    get_valuation_dashboard,
    snapshot_to_response,
)

router = APIRouter(prefix="/api/valuation", tags=["valuation"])


@router.get("/{code}/percentile", response_model=PercentileResponse)
def api_get_percentile(code: str, years: int = Query(default=10, ge=1, le=30)):
    history = fetch_pe_pb_history(code, years=years)
    result = calculate_percentiles(history)
    return PercentileResponse(**result)


@router.get("/{code}/snapshots", response_model=list[ValuationSnapshotResponse])
def api_list_snapshots(code: str, db: Session = Depends(get_db)):
    snapshots = (
        db.query(ValuationSnapshot)
        .filter(ValuationSnapshot.stock_code == code)
        .order_by(ValuationSnapshot.date.desc())
        .all()
    )
    return [ValuationSnapshotResponse(**snapshot_to_response(s)) for s in snapshots]


@router.get("/{code}/forward-dyr", response_model=ForwardDyrResponse)
def api_forward_dyr(code: str, db: Session = Depends(get_db)):
    return calculate_forward_dyr(db, code)


@router.get("/{code}/sustainability", response_model=SustainabilityResponse)
def api_check_sustainability(
    code: str,
    operating_cash_flow: float = Query(...),
    net_profit: float = Query(...),
    dividends_paid: float = Query(...),
):
    return check_dividend_sustainability(
        operating_cash_flow=operating_cash_flow,
        net_profit=net_profit,
        dividends_paid=dividends_paid,
    )


@router.get("/{code}/dashboard", response_model=DashboardResponse)
def api_get_dashboard(code: str, db: Session = Depends(get_db)):
    result = get_valuation_dashboard(db, code)
    return DashboardResponse(
        stock_code=result["stock_code"],
        latest_snapshot=(
            ValuationSnapshotResponse(**result["latest_snapshot"])
            if result.get("latest_snapshot")
            else None
        ),
        snapshots=[
            ValuationSnapshotResponse(**s) for s in result.get("snapshots", [])
        ],
        sustainability=(
            SustainabilityResponse(**result["sustainability"])
            if result.get("sustainability")
            else None
        ),
        composite=None,
        current_pe=result.get("current_pe"),
        current_pb=result.get("current_pb"),
        current_price=result.get("current_price"),
        dividend_yield=result.get("dividend_yield"),
        market_cap=result.get("market_cap"),
    )
