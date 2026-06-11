"""Monthly/quarterly/annual review endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.review import ReviewResponse
from app.services import review_service
from app.services.periodic_review_service import quarterly_review, annual_review

router = APIRouter(prefix="/api/review", tags=["review"])


@router.get("", response_model=ReviewResponse)
def get_monthly_review(
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    entry_limit: int = Query(default=200, ge=10, le=500),
    db: Session = Depends(get_db),
) -> dict:
    summary = review_service.compute(db, year_month=month, entry_limit=entry_limit)
    return {
        "month": summary.month,
        "drafts": {
            "triggered": summary.drafts_triggered,
            "executed": summary.drafts_executed,
            "cancelled": summary.drafts_cancelled,
            "hit_rate": summary.hit_rate,
            "buy": summary.buy_drafts,
            "sell": summary.sell_drafts,
        },
        "plans": {
            "created": summary.plans_created,
            "invalidated": summary.plans_invalidated,
            "status_changed": summary.plans_status_changed,
        },
        "holdings": {
            "created": summary.holdings_created,
            "sold": summary.holdings_sold,
        },
        "cashflow_goal_updates": summary.cashflow_goal_updates,
        "by_stock": summary.by_stock,
        "entries": summary.entries,
        "cycle": (
            {
                "cycle_position": summary.cycle.cycle_position,
                "pe_pct_10y": summary.cycle.pe_pct_10y,
                "position_range": summary.cycle.position_range,
                "position_advice": summary.cycle.position_advice,
            }
            if summary.cycle else None
        ),
        "thesis_alerts": [a.to_dict() for a in summary.thesis_alerts],
    }


@router.get("/quarterly", response_model=ReviewResponse)
def get_quarterly_review(
    year: int = Query(..., ge=2020, le=2030),
    q: int = Query(..., ge=1, le=4),
    db: Session = Depends(get_db),
) -> dict:
    return quarterly_review(db, year, q)


@router.get("/annual", response_model=ReviewResponse)
def get_annual_review(
    year: int = Query(..., ge=2020, le=2030),
    db: Session = Depends(get_db),
) -> dict:
    return annual_review(db, year)
