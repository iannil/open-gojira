"""Single aggregator endpoint that feeds the Cockpit main dashboard.

v2 (2026-06-25, Phase 3): 信号优先 dashboard (decision 19). Aggregates
v2-valid sources via cockpit_service.build — pending drafts, portfolio,
lifecycle counts, in-app alerts, recent research reports.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import cockpit_service

router = APIRouter(prefix="/api/cockpit", tags=["cockpit"])


@router.get("")
def get_cockpit(db: Session = Depends(get_db)) -> dict:
    """v2 信号优先 dashboard: one query → one DTO (decision 19)."""
    return cockpit_service.build(db)
