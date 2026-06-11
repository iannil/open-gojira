"""Strategy CRUD router."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import strategy_service
from app.schemas.strategy import (
    StrategyCreate,
    StrategyResponse,
    StrategyRule,
    StrategyTestRequest,
    StrategyTestResponse,
    StrategyUpdate,
)

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


def _to_response(s) -> StrategyResponse:
    from app.schemas.strategy import StrategyRule
    rule = StrategyRule.model_validate_json(s.rule_json)
    return StrategyResponse(
        id=s.id,
        name=s.name,
        slug=s.slug,
        description=s.description,
        kind=s.kind,
        rule=rule,
        is_builtin=s.is_builtin,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


@router.get("", response_model=list[StrategyResponse])
def list_strategies(db: Session = Depends(get_db)):
    return [_to_response(s) for s in strategy_service.list_all(db)]


@router.post("", response_model=StrategyResponse, status_code=201)
def create_strategy(payload: StrategyCreate, db: Session = Depends(get_db)):
    if strategy_service.get_by_slug(db, payload.slug):
        raise HTTPException(409, f"slug '{payload.slug}' already exists")
    s = strategy_service.create(db, payload)
    return _to_response(s)


@router.get("/{strategy_id}", response_model=StrategyResponse)
def get_strategy(strategy_id: int, db: Session = Depends(get_db)):
    s = strategy_service.get_by_id(db, strategy_id)
    if s is None:
        raise HTTPException(404, "strategy not found")
    return _to_response(s)


@router.put("/{strategy_id}", response_model=StrategyResponse)
def update_strategy(strategy_id: int, payload: StrategyUpdate, db: Session = Depends(get_db)):
    s = strategy_service.get_by_id(db, strategy_id)
    if s is None:
        raise HTTPException(404, "strategy not found")
    if s.is_builtin:
        raise HTTPException(403, "cannot modify built-in strategy")
    s = strategy_service.update(db, s, payload)
    return _to_response(s)


@router.delete("/{strategy_id}", status_code=204)
def delete_strategy(strategy_id: int, db: Session = Depends(get_db)):
    s = strategy_service.get_by_id(db, strategy_id)
    if s is None:
        raise HTTPException(404, "strategy not found")
    if s.is_builtin:
        raise HTTPException(403, "cannot delete built-in strategy")
    strategy_service.delete(db, s)


@router.post("/{strategy_id}/test", response_model=StrategyTestResponse)
def test_strategy(strategy_id: int, payload: StrategyTestRequest, db: Session = Depends(get_db)):
    s = strategy_service.get_by_id(db, strategy_id)
    if s is None:
        raise HTTPException(404, "strategy not found")
    from app.services.stock_context_builder import build_context
    from app.services.strategy_engine import evaluate
    rule = StrategyRule.model_validate_json(s.rule_json)
    ctx = build_context(db, payload.stock_code)
    result = evaluate(rule, ctx)
    return {
        "stock_code": ctx.code,
        "stock_name": ctx.name,
        "passed": result.passed,
        "conditions": [
            {"field": r.field, "passed": r.passed, "detail": r.detail}
            for r in result.condition_results
        ],
    }
