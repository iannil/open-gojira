"""Plan CRUD service — unified screening + trading plan.

A Plan combines strategies (screening) with optional trading rules.
Plans are not versioned — editing updates in place.
"""

from __future__ import annotations

import json
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.candidate import Candidate
from app.models.plan import Plan
from app.models.strategy import Strategy
from app.schemas.plan import (
    PlanCreate,
    PlanResponse,
    PlanUpdate,
    ScanScope,
    StrategyComposition,
    TradingRules,
)


def list_all(db: Session) -> list[Plan]:
    return list(db.execute(select(Plan).order_by(Plan.id)).scalars().all())


def list_active(db: Session) -> list[Plan]:
    return list(
        db.execute(
            select(Plan).where(Plan.status == "active").order_by(Plan.id)
        ).scalars().all()
    )


def get_by_id(db: Session, plan_id: int) -> Plan | None:
    return db.get(Plan, plan_id)


def get_by_slug(db: Session, slug: str) -> Plan | None:
    return db.execute(
        select(Plan).where(Plan.slug == slug)
    ).scalar_one_or_none()


def create(db: Session, data: PlanCreate) -> Plan:
    # Validate strategy IDs exist
    for sid in data.strategy_composition.strategy_ids:
        if db.get(Strategy, sid) is None:
            raise HTTPException(400, f"strategy {sid} not found")

    plan = Plan(
        name=data.name,
        slug=data.slug,
        description=data.description,
        status="active",
        strategy_composition_json=data.strategy_composition.model_dump_json(),
        scan_scope_json=data.scan_scope.model_dump_json(),
        schedule_cron=data.schedule_cron,
        trading_rules_json=(
            data.trading_rules.model_dump_json() if data.trading_rules else None
        ),
        is_builtin=False,
    )
    db.add(plan)
    db.flush()
    return plan


def update(db: Session, plan: Plan, data: PlanUpdate) -> Plan:
    if plan.is_builtin and data.strategy_composition is not None:
        raise HTTPException(403, "cannot modify built-in plan strategies")

    if data.name is not None:
        plan.name = data.name
    if data.description is not None:
        plan.description = data.description
    if data.status is not None:
        plan.status = data.status
    if data.strategy_composition is not None:
        for sid in data.strategy_composition.strategy_ids:
            if db.get(Strategy, sid) is None:
                raise HTTPException(400, f"strategy {sid} not found")
        plan.strategy_composition_json = data.strategy_composition.model_dump_json()
    if data.scan_scope is not None:
        plan.scan_scope_json = data.scan_scope.model_dump_json()
    if data.schedule_cron is not None:
        plan.schedule_cron = data.schedule_cron
    if data.trading_rules is not None:
        plan.trading_rules_json = data.trading_rules.model_dump_json()
    db.flush()
    return plan


def delete(db: Session, plan: Plan) -> None:
    if plan.is_builtin:
        raise HTTPException(403, "cannot delete built-in plan")
    db.delete(plan)
    db.flush()


def parse_composition(plan: Plan) -> StrategyComposition:
    return StrategyComposition.model_validate_json(plan.strategy_composition_json)


def parse_scope(plan: Plan) -> ScanScope:
    return ScanScope.model_validate_json(plan.scan_scope_json)


def parse_trading_rules(plan: Plan) -> TradingRules | None:
    if plan.trading_rules_json is None:
        return None
    return TradingRules.model_validate_json(plan.trading_rules_json)


def to_response(plan: Plan) -> PlanResponse:
    comp = parse_composition(plan)
    scope = parse_scope(plan)
    rules = parse_trading_rules(plan)
    summary = None
    if plan.last_run_summary:
        try:
            summary = json.loads(plan.last_run_summary)
        except (json.JSONDecodeError, TypeError):
            pass
    return PlanResponse(
        id=plan.id,
        name=plan.name,
        slug=plan.slug,
        description=plan.description,
        status=plan.status,
        strategy_composition=comp,
        scan_scope=scope,
        schedule_cron=plan.schedule_cron,
        trading_rules=rules,
        last_run_at=plan.last_run_at,
        last_run_summary=summary,
        is_builtin=plan.is_builtin,
        candidate_count=len([c for c in plan.candidates if c.status == "active"]) if plan.candidates else 0,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )
