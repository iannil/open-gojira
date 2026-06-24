"""Single aggregator endpoint that feeds the Cockpit main dashboard.

v2 (2026-06-24): stubbed. v1 cockpit_service removed (used deleted v1 models).
Will be replaced by v2 signal-first dashboard in Phase 3.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter(prefix="/api/cockpit", tags=["cockpit"])


@router.get("")
def get_cockpit(db: Session = Depends(get_db)) -> dict:
    """v2 stub: returns empty cockpit. To be implemented in Phase 3."""
    return {
        "status": "v2_stub",
        "message": "Cockpit will be rebuilt in Phase 3 (signal-first dashboard)",
        "signals": [],
        "holdings": [],
        "candidates": [],
        "watchlist": [],
    }
