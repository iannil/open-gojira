"""Strategy rule DSL and CRUD schemas."""

from __future__ import annotations

from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator


# ── Strategy Rule DSL ────────────────────────────────────────────────

StrategyField = Literal[
    "dyr",
    "dyr_fwd",
    "pe_pct_10y",
    "pb_pct_10y",
    "dividend_sustainability",
    "ocf_to_ni",
    "qiu_score",
    "industry_in",
    "security_theme_in",
    "bank_blind_box",
    "price_drop_pct",
    "hq_region_tier",
    "market_temperature",
    "has_mine",
    "domestic_leader",
]

ComparisonOp = Literal[">=", "<=", "==", "in"]


class Condition(BaseModel):
    field: StrategyField
    op: ComparisonOp
    value: Union[bool, float, str, list[str]]

    @model_validator(mode="after")
    def _validate_value_type(self) -> "Condition":
        if self.op == "in":
            if not isinstance(self.value, list):
                raise ValueError("'in' op requires a list value")
        elif isinstance(self.value, list):
            raise ValueError(f"'{self.op}' op requires a scalar value")
        return self


class StrategyRule(BaseModel):
    logic: Literal["AND", "OR"]
    conditions: list[Condition] = Field(min_length=1)


class ConditionResult(BaseModel):
    field: StrategyField
    passed: bool
    actual_value: Any = None
    threshold: Any = None
    detail: str = ""


class EvalResult(BaseModel):
    passed: bool
    condition_results: list[ConditionResult] = Field(default_factory=list)


# ── CRUD schemas ─────────────────────────────────────────────────────

class StrategyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_]*$")
    description: str = ""
    rule: StrategyRule


class StrategyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    rule: Optional[StrategyRule] = None


class StrategyResponse(BaseModel):
    id: int
    name: str
    slug: str
    description: str
    kind: str
    rule: StrategyRule
    is_builtin: bool
    created_at: Any = None
    updated_at: Any = None


class StrategyTestRequest(BaseModel):
    stock_code: str = Field(min_length=1)


class StrategyTestConditionResult(BaseModel):
    field: StrategyField
    passed: bool
    detail: str = ""


class StrategyTestResponse(BaseModel):
    stock_code: str
    stock_name: str
    passed: bool
    conditions: list[StrategyTestConditionResult]
