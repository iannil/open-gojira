"""Portfolio rebalancing service — "仓位控制高于一切".

Compares actual vs target weights at two levels:
1. Quadrant level: actual quadrant weights vs cashflow_goal.quadrant_targets_json
2. Theme level: actual theme weights vs theme.target_weight_pct

Position-level rebalancing was based on per-stock Plans which no longer exist
in the strategy-driven system. It will be redesigned in a future iteration.
"""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.services import (
    cashflow_service,
    cashflow_goal_service,
    holding_service,
    theme_service,
)

logger = logging.getLogger(__name__)


class RebalanceSuggestion(BaseModel):
    """A single rebalancing action suggestion."""

    level: str  # "quadrant" | "theme"
    code: str | None = None
    quadrant: str | None = None
    theme: str | None = None
    current_pct: float = 0.0
    target_pct: float = 0.0
    drift_pct: float = 0.0
    action: str = ""
    priority: str = "low"


def _parse_quadrant_targets(goal) -> dict[str, float]:
    if not goal or not goal.quadrant_targets_json:
        return {}
    try:
        data = json.loads(goal.quadrant_targets_json)
        return {k: float(v) for k, v in data.items()}
    except (json.JSONDecodeError, ValueError, TypeError):
        logger.warning("Failed to parse quadrant_targets_json for cashflow goal")
        return {}


def _priority_from_drift(drift_pct: float) -> str:
    abs_drift = abs(drift_pct)
    if abs_drift >= 0.10:
        return "high"
    elif abs_drift >= 0.05:
        return "medium"
    return "low"


def compute_rebalancing_suggestions(
    db: Session, drift_threshold: float = 0.05
) -> list[RebalanceSuggestion]:
    suggestions: list[RebalanceSuggestion] = []

    # 1. Quadrant level
    goal = cashflow_goal_service.get_or_create(db)
    quadrant_targets = _parse_quadrant_targets(goal)

    if quadrant_targets:
        quadrant_breakdown = cashflow_service.quadrant_breakdown(db)
        quadrant_actual = {
            q["quadrant"]: q["weight_pct"] / 100.0
            for q in quadrant_breakdown
        }

        for quadrant, target_pct in quadrant_targets.items():
            current_pct = quadrant_actual.get(quadrant, 0.0)
            drift_pct = current_pct - target_pct

            if abs(drift_pct) < drift_threshold:
                continue

            action = "减持" if drift_pct > 0 else "增持"
            priority = _priority_from_drift(drift_pct)

            suggestions.append(
                RebalanceSuggestion(
                    level="quadrant",
                    quadrant=quadrant,
                    current_pct=current_pct,
                    target_pct=target_pct,
                    drift_pct=drift_pct,
                    action=action,
                    priority=priority,
                )
            )

    # 2. Theme level
    theme_targets = theme_service.get_theme_targets(db)

    for tt in theme_targets:
        theme_name = tt["theme"]
        target_pct = tt["target_pct"] / 100.0
        actual_pct = tt["actual_pct"] / 100.0
        drift_pct = actual_pct - target_pct

        if abs(drift_pct) < drift_threshold:
            continue

        action = "减持" if drift_pct > 0 else "增持"
        priority = _priority_from_drift(drift_pct)

        suggestions.append(
            RebalanceSuggestion(
                level="theme",
                theme=theme_name,
                current_pct=actual_pct,
                target_pct=target_pct,
                drift_pct=drift_pct,
                action=action,
                priority=priority,
            )
        )

    suggestions.sort(key=lambda s: abs(s.drift_pct), reverse=True)
    return suggestions


def generate_rebalancing_alerts(
    db: Session, drift_threshold: float = 0.05
) -> dict:
    """Generate rebalancing suggestions and return summary."""
    suggestions = compute_rebalancing_suggestions(db, drift_threshold)

    high_priority = [s for s in suggestions if s.priority == "high"]
    medium_priority = [s for s in suggestions if s.priority == "medium"]

    return {
        "total_suggestions": len(suggestions),
        "high_priority": len(high_priority),
        "medium_priority": len(medium_priority),
        "drafts_created": 0,
        "suggestions": [s.model_dump() for s in suggestions],
    }
