"""Market data endpoints — indices, index K-line, cycle assessment."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.market import (
    CycleAssessmentResponse,
    DividendProjectionResponse,
    IndexKlineResponse,
    ThesisAlertResponse,
)
from app.services.cycle_assessment_service import assess_cycle
from app.services.lixinger_client import LixingerError, get_lixinger_client
from app.services.market_service import fetch_market_indices

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/indices", response_model=list[dict])
def api_get_market_indices():
    """Get current data for major A-share indices."""
    return fetch_market_indices()


@router.get("/index/{code}/kline", response_model=IndexKlineResponse)
def api_get_index_kline(code: str, days: int = 365):
    """Daily K-line for an index (benchmark for individual stocks)."""
    start = (date.today() - timedelta(days=max(1, days))).isoformat()
    try:
        rows = get_lixinger_client().get_index_kline(stock_code=code, start_date=start)
    except LixingerError as e:
        raise HTTPException(status_code=502, detail=f"Lixinger error: {e}")
    return {
        "stock_code": code,
        "points": [
            {
                "date": str(r.get("date", ""))[:10],
                "open": r.get("open"),
                "high": r.get("high"),
                "low": r.get("low"),
                "close": r.get("close"),
                "volume": r.get("volume"),
            }
            for r in rows or []
        ],
    }


@router.get("/cycle", response_model=CycleAssessmentResponse)
def api_get_cycle_assessment(db: Session = Depends(get_db)):
    """Current market cycle assessment (PE percentile based)."""
    assessment = assess_cycle(db)
    return assessment.model_dump()


@router.get("/dividend-projection", response_model=DividendProjectionResponse)
def api_get_dividend_projection(db: Session = Depends(get_db)):
    """Projected dividend income for next 12 months."""
    from app.services.dividend_projector_service import project
    return project(db).model_dump()


@router.get("/thesis-alerts", response_model=list[ThesisAlertResponse])
def api_get_thesis_alerts(db: Session = Depends(get_db)):
    """Check thesis variable thresholds for all held stocks."""
    from app.services.thesis_monitor_service import check_held_stocks
    alerts = check_held_stocks(db)
    return [a.model_dump() for a in alerts]
