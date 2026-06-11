"""Plan CRUD router — unified screening + trading plan."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.candidate import CandidateResponse
from app.schemas.plan import PlanCreate, PlanResponse, PlanUpdate
from app.services import candidate_service, plan_service

router = APIRouter(prefix="/api/plans", tags=["plans"])


@router.get("", response_model=list[PlanResponse])
def list_plans(db: Session = Depends(get_db)):
    return [plan_service.to_response(p) for p in plan_service.list_all(db)]


@router.post("", response_model=PlanResponse, status_code=201)
def create_plan(payload: PlanCreate, db: Session = Depends(get_db)):
    existing = plan_service.get_by_slug(db, payload.slug)
    if existing:
        raise HTTPException(409, f"slug '{payload.slug}' already exists")
    p = plan_service.create(db, payload)
    return plan_service.to_response(p)


@router.get("/{plan_id}", response_model=PlanResponse)
def get_plan(plan_id: int, db: Session = Depends(get_db)):
    p = plan_service.get_by_id(db, plan_id)
    if p is None:
        raise HTTPException(404, "plan not found")
    return plan_service.to_response(p)


@router.put("/{plan_id}", response_model=PlanResponse)
def update_plan(plan_id: int, payload: PlanUpdate, db: Session = Depends(get_db)):
    p = plan_service.get_by_id(db, plan_id)
    if p is None:
        raise HTTPException(404, "plan not found")
    p = plan_service.update(db, p, payload)
    return plan_service.to_response(p)


@router.delete("/{plan_id}", status_code=204)
def delete_plan(plan_id: int, db: Session = Depends(get_db)):
    p = plan_service.get_by_id(db, plan_id)
    if p is None:
        raise HTTPException(404, "plan not found")
    plan_service.delete(db, p)


@router.post("/{plan_id}/run")
def run_plan(plan_id: int, db: Session = Depends(get_db)):
    p = plan_service.get_by_id(db, plan_id)
    if p is None:
        raise HTTPException(404, "plan not found")
    from app.services.plan_runner import run_plan as _run
    result = _run(db, p)
    return {
        "plan_id": result.plan_id,
        "plan_name": result.plan_name,
        "scanned": result.scanned,
        "passed": result.passed,
        "removed": result.removed,
        "new": result.new,
        "drafts_emitted": result.drafts_emitted,
        "errors": result.errors,
    }


@router.get("/{plan_id}/candidates", response_model=list[CandidateResponse])
def list_plan_candidates(plan_id: int, db: Session = Depends(get_db)):
    from app.routers.candidates import _to_response
    return [_to_response(c) for c in candidate_service.list_for_plan(db, plan_id)]
