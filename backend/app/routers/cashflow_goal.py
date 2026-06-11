"""Cashflow-goal singleton endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.cashflow_goal import CashflowGoalResponse, CashflowGoalUpdate
from app.services import audit_log_service, cashflow_goal_service

router = APIRouter(prefix="/api/cashflow-goal", tags=["cashflow_goal"])


def _to_response(goal) -> CashflowGoalResponse:
    return CashflowGoalResponse(
        annual_expense=float(goal.annual_expense),
        goal_multiple=float(goal.goal_multiple),
        currency=goal.currency,
        notes=goal.notes,
        target_annual_cashflow=cashflow_goal_service.target_annual_cashflow(goal),
        updated_at=goal.updated_at,
    )


@router.get("", response_model=CashflowGoalResponse)
def get_goal(db: Session = Depends(get_db)) -> CashflowGoalResponse:
    goal = cashflow_goal_service.get_or_create(db)
    db.commit()
    return _to_response(goal)


@router.put("", response_model=CashflowGoalResponse)
def update_goal(
    payload: CashflowGoalUpdate,
    db: Session = Depends(get_db),
) -> CashflowGoalResponse:
    goal = cashflow_goal_service.update(
        db,
        annual_expense=payload.annual_expense,
        goal_multiple=payload.goal_multiple,
        currency=payload.currency,
        notes=payload.notes,
        cash_reserve=payload.cash_reserve,
    )
    audit_log_service.write(
        db,
        entity_type="cashflow_goal",
        entity_id=str(goal.id),
        event="updated",
        actor="user",
        summary=(
            f"annual_expense={goal.annual_expense} "
            f"goal_multiple={goal.goal_multiple} "
            f"currency={goal.currency}"
        ),
        payload=payload.model_dump(exclude_none=True),
    )
    db.commit()
    return _to_response(goal)
