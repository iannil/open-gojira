"""Single aggregator endpoint that feeds the Cockpit main dashboard."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.cockpit import CockpitResponse
from app.services import cockpit_service

router = APIRouter(prefix="/api/cockpit", tags=["cockpit"])


@router.get("", response_model=CockpitResponse)
def get_cockpit(db: Session = Depends(get_db)) -> CockpitResponse:
    return cockpit_service.build(db)
