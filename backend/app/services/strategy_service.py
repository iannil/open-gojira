"""Strategy CRUD service."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.strategy import Strategy
from app.schemas.strategy import StrategyCreate, StrategyRule, StrategyUpdate


def list_all(db: Session) -> list[Strategy]:
    return list(db.execute(select(Strategy).order_by(Strategy.id)).scalars().all())


def get_by_id(db: Session, strategy_id: int) -> Strategy | None:
    return db.get(Strategy, strategy_id)


def get_by_slug(db: Session, slug: str) -> Strategy | None:
    return db.execute(
        select(Strategy).where(Strategy.slug == slug)
    ).scalar_one_or_none()


def create(db: Session, data: StrategyCreate) -> Strategy:
    rule_json = data.rule.model_dump_json()
    strategy = Strategy(
        name=data.name,
        slug=data.slug,
        description=data.description,
        kind="custom",
        rule_json=rule_json,
        is_builtin=False,
    )
    db.add(strategy)
    db.flush()
    return strategy


def update(db: Session, strategy: Strategy, data: StrategyUpdate) -> Strategy:
    if data.name is not None:
        strategy.name = data.name
    if data.description is not None:
        strategy.description = data.description
    if data.rule is not None:
        strategy.rule_json = data.rule.model_dump_json()
    db.flush()
    return strategy


def delete(db: Session, strategy: Strategy) -> None:
    db.delete(strategy)
    db.flush()


def parse_rule(rule_json: str) -> StrategyRule:
    return StrategyRule.model_validate_json(rule_json)
