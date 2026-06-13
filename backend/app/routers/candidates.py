"""Candidate CRUD router."""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.candidate import Candidate
from app.services import candidate_service
from app.schemas.candidate import CandidateResponse, CandidateUpdate

router = APIRouter(prefix="/api/candidates", tags=["candidates"])


def _to_response(c: Candidate) -> CandidateResponse:
    stock = c.stock
    plan = c.plan
    last_eval = None
    if c.last_eval_json:
        try:
            last_eval = json.loads(c.last_eval_json)
        except Exception:
            pass
    return CandidateResponse(
        id=c.id,
        plan_id=c.plan_id,
        plan_name=plan.name if plan else "",
        stock_code=c.stock_code,
        stock_name=stock.name if stock else "",
        stock_industry=stock.industry if stock else None,
        stock_security_theme=stock.security_theme if stock else None,
        stock_quadrant=stock.quadrant if stock else None,
        stock_tier=stock.tier if stock else None,
        stock_qiu_score=stock.qiu_score if stock else 0,
        stock_hq_region=stock.hq_region if stock else None,
        status=c.status,
        first_seen_at=c.first_seen_at,
        last_confirmed_at=c.last_confirmed_at,
        last_eval=last_eval,
        pinned=c.pinned,
        notes=c.notes,
    )


@router.get("", response_model=list[CandidateResponse])
def list_candidates(
    plan_id: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    return [_to_response(c) for c in candidate_service.list_all(db, plan_id=plan_id, status=status)]


@router.get("/{candidate_id}", response_model=CandidateResponse)
def get_candidate(candidate_id: int, db: Session = Depends(get_db)):
    c = candidate_service.get_by_id(db, candidate_id)
    if c is None:
        raise HTTPException(404, "candidate not found")
    return _to_response(c)


@router.put("/{candidate_id}", response_model=CandidateResponse)
def update_candidate(candidate_id: int, payload: CandidateUpdate, db: Session = Depends(get_db)):
    c = candidate_service.get_by_id(db, candidate_id)
    if c is None:
        raise HTTPException(404, "candidate not found")
    c = candidate_service.update(db, c, pinned=payload.pinned, notes=payload.notes)
    return _to_response(c)


@router.delete("/{candidate_id}", status_code=204)
def remove_candidate(candidate_id: int, db: Session = Depends(get_db)):
    c = candidate_service.get_by_id(db, candidate_id)
    if c is None:
        raise HTTPException(404, "candidate not found")
    candidate_service.remove(db, c)
