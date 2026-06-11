"""Thesis monitor service — 论点变量阈值越界检测.

Extends thesis_variables_json with threshold definitions and checks for
breaches. Aligns with invest1 "第一性原理" — each industry has one core variable.

Expected thesis_variables_json format:
{
  "variables": [
    {"name": "煤油比", "value": 3.5, "unit": "倍",
     "threshold_low": 2.0, "threshold_critical": 1.5, "direction": "above"}
  ]
}
"""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.holding import Holding
from app.models.stock import Stock

logger = logging.getLogger(__name__)


class ThesisAlert(BaseModel):
    code: str
    stock_name: str
    variable_name: str
    current_value: float | None
    threshold_type: str  # "warning" | "critical"
    threshold_value: float
    direction: str  # "above" | "below"
    message: str


def parse_thesis_variables(raw: str | None) -> list[dict]:
    """Parse thesis_variables_json into a list of variable dicts."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data.get("variables", [])
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, TypeError):
        logger.warning("Failed to parse thesis_variables_json: %s", raw[:100])
    return []


def check_variable(var: dict) -> str | None:
    """Check a single thesis variable against its thresholds.

    Returns: "critical", "warning", or None (within range).
    """
    value = var.get("value")
    if value is None:
        return None

    direction = var.get("direction", "above")
    threshold_critical = var.get("threshold_critical")
    threshold_low = var.get("threshold_low")
    threshold_high = var.get("threshold_high")

    if direction == "above":
        # Value should stay above threshold
        if threshold_critical is not None and value < threshold_critical:
            return "critical"
        if threshold_low is not None and value < threshold_low:
            return "warning"
    elif direction == "below":
        # Value should stay below threshold
        if threshold_critical is not None and value > threshold_critical:
            return "critical"
        if threshold_high is not None and value > threshold_high:
            return "warning"

    return None


def check_held_stocks(db: Session) -> list[ThesisAlert]:
    """Check thesis variables for all open holdings."""
    holdings = list(
        db.execute(
            select(Holding).where(Holding.sell_date.is_(None))
        ).scalars().all()
    )

    alerts: list[ThesisAlert] = []

    for h in holdings:
        stock = db.get(Stock, h.stock_code)
        if not stock or not stock.thesis_variables_json:
            continue

        variables = parse_thesis_variables(stock.thesis_variables_json)
        for var in variables:
            severity = check_variable(var)
            if severity is None:
                continue

            name = var.get("name", "未知变量")
            value = var.get("value")
            direction = var.get("direction", "above")

            if severity == "critical":
                threshold = var.get("threshold_critical", 0)
            else:
                threshold = var.get("threshold_low") or var.get("threshold_high", 0)

            if direction == "above" and severity:
                message = f"{stock.name}({h.stock_code}) {name}={value}，低于{severity}阈值{threshold}"
            else:
                message = f"{stock.name}({h.stock_code}) {name}={value}，超过{severity}阈值{threshold}"

            alerts.append(ThesisAlert(
                code=h.stock_code,
                stock_name=stock.name or h.stock_code,
                variable_name=name,
                current_value=value,
                threshold_type=severity,
                threshold_value=threshold,
                direction=direction,
                message=message,
            ))

    return alerts
