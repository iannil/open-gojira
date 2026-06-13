"""Risk rules API — CRUD for holding_risk_rules (S5.4).

Per-stock stop-loss / take-profit rules. The scheduler's
intraday_price_poll job evaluates these against realtime prices and
emits system_alerts when triggered.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.holding_risk_rule import HoldingRiskRule

router = APIRouter(prefix="/api/risk-rules", tags=["risk-rules"])


# ── Schemas ───────────────────────────────────────────────────────────────


class RiskRuleResponse(BaseModel):
    id: int
    stock_code: str
    stop_loss_pct: float | None
    stop_loss_type: str
    take_profit_pct: float | None
    take_profit_type: str
    peak_price: float | None
    enabled: bool
    triggered_at: datetime | None
    trigger_reason: str | None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class RiskRuleCreate(BaseModel):
    stock_code: str
    stop_loss_pct: float | None = None
    stop_loss_type: str = "pct_from_cost"
    take_profit_pct: float | None = None
    take_profit_type: str = "pct_from_cost"
    enabled: bool = True


class RiskRuleUpdate(BaseModel):
    stop_loss_pct: float | None = None
    stop_loss_type: str | None = None
    take_profit_pct: float | None = None
    take_profit_type: str | None = None
    enabled: bool | None = None
    peak_price: float | None = None  # allow manual reset for trailing


# ── Endpoints ─────────────────────────────────────────────────────────────


@router.get("", response_model=list[RiskRuleResponse])
def list_rules(db: Session = Depends(get_db)) -> list[HoldingRiskRule]:
    return list(
        db.execute(
            select(HoldingRiskRule).order_by(HoldingRiskRule.stock_code)
        ).scalars().all()
    )


@router.get("/{stock_code}", response_model=RiskRuleResponse | None)
def get_rule(
    stock_code: str, db: Session = Depends(get_db)
) -> HoldingRiskRule | None:
    return db.execute(
        select(HoldingRiskRule).where(HoldingRiskRule.stock_code == stock_code)
    ).scalar_one_or_none()


@router.post("", response_model=RiskRuleResponse, status_code=201)
def create_rule(
    payload: RiskRuleCreate, db: Session = Depends(get_db)
) -> HoldingRiskRule:
    existing = db.execute(
        select(HoldingRiskRule).where(HoldingRiskRule.stock_code == payload.stock_code)
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(409, f"Rule for {payload.stock_code} already exists")
    rule = HoldingRiskRule(**payload.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.patch("/{rule_id}", response_model=RiskRuleResponse)
def update_rule(
    rule_id: int, payload: RiskRuleUpdate, db: Session = Depends(get_db)
) -> HoldingRiskRule:
    rule = db.get(HoldingRiskRule, rule_id)
    if not rule:
        raise HTTPException(404, f"rule {rule_id} not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(rule, k, v)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/{rule_id}", status_code=204)
def delete_rule(rule_id: int, db: Session = Depends(get_db)) -> None:
    rule = db.get(HoldingRiskRule, rule_id)
    if not rule:
        raise HTTPException(404, f"rule {rule_id} not found")
    db.delete(rule)
    db.commit()
