"""Strategy engine — pure function evaluator for strategy rules.

Takes a StrategyRule and a StockContext, returns an EvalResult.
No DB access, no side effects — fully testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.schemas.strategy import Condition, EvalResult, ConditionResult, StrategyRule


@dataclass
class StockContext:
    """In-memory snapshot of a stock's data for strategy evaluation."""

    code: str
    name: str = ""
    industry: str | None = None
    security_theme: str | None = None
    tier: str | None = None
    qiu_score: int | None = None
    hq_region: str | None = None

    # Valuation
    dyr: float | None = None
    forward_dyr: float | None = None
    pe_pct_10y: float | None = None
    pb_pct_10y: float | None = None

    # G4: resource flags (invest3 §12)
    has_mine: bool | None = None
    domestic_leader: bool | None = None
    # B2: resource v2 flags (invest3 §12 资源股 7 维剩 2 维)
    expansion_outlook: bool | None = None
    geo_risk: bool | None = None

    # C1: effective "求"字位阶 (power_tier_baseline from pattern OR qiu_score override)
    power_tier: int | None = None

    # Financial
    dividend_sustainability: float | None = None
    ocf_to_ni: float | None = None

    # Price
    price: float | None = None
    price_52w_high: float | None = None
    price_drop_pct: float | None = None

    # Special
    bank_blind_box: str | None = None  # "可见" | "模糊" | "不可见"
    market_temperature: float | None = None
    # D3 (2026-06-17 invest-alignment): 财报红旗数 (invest1 §三 + invest2 §10)
    red_flag_count: int | None = None
    # B4-4 N4 (invest3 §八第2节): forward 分红承诺
    dividend_payout_commitment_pct: float | None = None


def _resolve_field(ctx: StockContext, field: str) -> Any:
    """Map field name to StockContext attribute value."""
    mapping = {
        "dyr": ctx.dyr,
        "dyr_fwd": ctx.forward_dyr,
        "pe_pct_10y": ctx.pe_pct_10y,
        "pb_pct_10y": ctx.pb_pct_10y,
        "dividend_sustainability": ctx.dividend_sustainability,
        "ocf_to_ni": ctx.ocf_to_ni,
        "qiu_score": ctx.qiu_score,
        "industry_in": ctx.industry,
        "security_theme_in": ctx.security_theme,
        "bank_blind_box": ctx.bank_blind_box,
        "price_drop_pct": ctx.price_drop_pct,
        "hq_region_tier": ctx.hq_region,
        "market_temperature": ctx.market_temperature,
        "has_mine": ctx.has_mine,
        "domestic_leader": ctx.domestic_leader,
        "expansion_outlook": ctx.expansion_outlook,
        "geo_risk": ctx.geo_risk,
        "power_tier": ctx.power_tier,
        "red_flag_count": ctx.red_flag_count,
        "dividend_payout_commitment_pct": ctx.dividend_payout_commitment_pct,
    }
    return mapping.get(field)


def _evaluate_condition(cond: Condition, ctx: StockContext) -> ConditionResult:
    """Evaluate a single condition against a stock context."""
    actual = _resolve_field(ctx, cond.field)

    # Field not available
    if actual is None:
        return ConditionResult(
            field=cond.field,
            passed=False,
            actual_value=None,
            threshold=cond.value,
            detail=f"{cond.field}: data unavailable",
        )

    if cond.op == "in":
        # actual is a single value (e.g. industry), value is a list
        if isinstance(cond.value, list):
            passed = actual in cond.value
        else:
            passed = False
        detail = f"{actual} {'∈' if passed else '∉'} {cond.value}"
    elif cond.op == "==":
        passed = str(actual) == str(cond.value)
        detail = f"{actual} {'==' if passed else '!='} {cond.value}"
    elif cond.op == ">=":
        passed = float(actual) >= float(cond.value)
        detail = f"{actual} {'≥' if passed else '<'} {cond.value}"
    elif cond.op == "<=":
        passed = float(actual) <= float(cond.value)
        detail = f"{actual} {'≤' if passed else '>'} {cond.value}"
    else:
        passed = False
        detail = f"unknown op: {cond.op}"

    return ConditionResult(
        field=cond.field,
        passed=passed,
        actual_value=actual,
        threshold=cond.value,
        detail=detail,
    )


def evaluate(rule: StrategyRule, ctx: StockContext) -> EvalResult:
    """Evaluate a strategy rule against a stock context. Pure function."""
    results = [_evaluate_condition(c, ctx) for c in rule.conditions]

    if rule.logic == "AND":
        passed = all(r.passed for r in results)
    else:  # OR
        passed = any(r.passed for r in results)

    return EvalResult(passed=passed, condition_results=results)
