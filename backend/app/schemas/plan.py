"""Plan schemas — unified screening + trading plan.

The Plan DSL for trading rules (buy/sell ladders, gates, invalidation) is
retained from the original design. The screening layer adds strategy
composition and scan scope configuration.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator


# ── Trading Rules DSL (reused from original) ─────────────────────────

BuyTriggerKind = Literal[
    "price_le",
    "dyr_ge",
    "dyr_fwd_ge",
    "drawdown_from_last_buy",
    "pe_pct_le",
]


class BuyTrigger(BaseModel):
    kind: BuyTriggerKind
    value: float = Field(gt=0)


SellTriggerKind = Literal[
    "profit_pct_ge",
    "dyr_le",
    "dyr_fwd_le",
    "pe_pct_ge",
    "cycle_position_ge",  # B1 (G1 v2): invest3 §5 "高位主动减仓"
]


class SellTrigger(BaseModel):
    kind: SellTriggerKind
    # B1: cycle_position_ge 用 cycle position 字符串 (extreme_low/low/mid/high/extreme_high);
    # 其他 op 用 float。Union[str, float] 兼容两种语义。
    value: Union[str, float]

    @model_validator(mode="after")
    def _validate_value(self) -> "SellTrigger":
        if self.kind == "cycle_position_ge":
            valid = {"extreme_low", "low", "mid", "high", "extreme_high"}
            if self.value not in valid:
                raise ValueError(
                    f"cycle_position_ge requires one of {valid}, got {self.value!r}"
                )
        else:
            if not isinstance(self.value, (int, float)) or isinstance(self.value, bool):
                raise ValueError(
                    f"{self.kind} requires numeric value, got {self.value!r}"
                )
            if self.value <= 0:
                raise ValueError(f"{self.kind} requires value > 0")
        return self


InvalidationKind = Literal[
    "ocf_to_ni_3y_lt",
    "dividend_cut_pct_ge",
    "thesis_manual_revoke",
]


class InvalidationRule(BaseModel):
    kind: InvalidationKind
    value: float = Field(default=0.0, ge=0)


class BuyStep(BaseModel):
    trigger: BuyTrigger
    add_pct: Annotated[float, Field(gt=0, le=1)]


class SellStep(BaseModel):
    trigger: SellTrigger
    reduce_pct_of_position: Annotated[float, Field(gt=0, le=1)]


class TradingRules(BaseModel):
    """Optional trading rules within a plan. Applied to watchlisted candidates."""
    buy_ladder: list[BuyStep] = Field(default_factory=list)
    sell_ladder: list[SellStep] = Field(default_factory=list)
    invalidation: list[InvalidationRule] = Field(default_factory=list)
    cooldown_days: int = Field(default=5, ge=0, le=90)

    @model_validator(mode="after")
    def _at_least_one_action(self) -> "TradingRules":
        if not self.buy_ladder and not self.sell_ladder:
            raise ValueError("trading rules must define at least one buy or sell step")
        return self


# ── Screening Configuration ──────────────────────────────────────────

class StrategyComposition(BaseModel):
    strategy_ids: list[int] = Field(min_length=1)
    logic: Literal["AND", "OR"] = "AND"


ScanScopeType = Literal[
    "all_stocks", "industries", "index", "watchlist", "custom",
    "business_pattern",  # C2: 按 BusinessPattern 圈定扫描范围
]


class ScanScope(BaseModel):
    type: ScanScopeType
    values: list[str] = Field(default_factory=list)
    """For 'business_pattern' type, values are pattern IDs as strings."""

    @model_validator(mode="after")
    def _validate_values(self) -> "ScanScope":
        if self.type == "all_stocks":
            pass  # values ignored
        elif self.type in ("industries", "index", "watchlist", "custom", "business_pattern"):
            if not self.values:
                raise ValueError(f"'{self.type}' scope requires non-empty values")
        return self


# ── CRUD schemas ─────────────────────────────────────────────────────

PlanStatus = Literal["active", "paused", "archived"]

# G1 cycle gate: 5 positions (rank 升序 = 越来越高估)
CycleBuyMax = Literal["extreme_low", "low", "mid", "high", "extreme_high"]


class PlanCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_]*$")
    description: str = ""
    strategy_composition: StrategyComposition
    scan_scope: ScanScope
    schedule_cron: str = "0 18 * * 1-5"
    trading_rules: Optional[TradingRules] = None
    cycle_buy_max: CycleBuyMax = "mid"
    disable_midstream_filter: bool = False


class PlanUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[PlanStatus] = None
    strategy_composition: Optional[StrategyComposition] = None
    scan_scope: Optional[ScanScope] = None
    schedule_cron: Optional[str] = None
    trading_rules: Optional[TradingRules] = None
    cycle_buy_max: Optional[CycleBuyMax] = None
    disable_midstream_filter: Optional[bool] = None


class PlanResponse(BaseModel):
    id: int
    name: str
    slug: str
    description: str
    status: PlanStatus
    strategy_composition: StrategyComposition
    scan_scope: ScanScope
    schedule_cron: str
    trading_rules: Optional[TradingRules] = None
    cycle_buy_max: CycleBuyMax = "mid"
    disable_midstream_filter: bool = False
    last_run_at: Any = None
    last_run_summary: Any = None
    is_builtin: bool
    candidate_count: int = 0
    created_at: Any = None
    updated_at: Any = None


# ── Draft schemas ────────────────────────────────────────────────────

DraftSide = Literal["BUY", "SELL"]
DraftStatus = Literal["pending", "executed", "cancelled", "superseded"]


class DraftResponse(BaseModel):
    id: int
    plan_id: int
    code: str
    side: DraftSide
    status: DraftStatus
    step_kind: str
    step_index: int
    add_pct: Optional[float] = None
    reduce_pct_of_position: Optional[float] = None
    suggested_quantity: Optional[int] = None
    reason: str
    source: str = "evaluator"
    triggered_at: Any
    executed_at: Optional[Any] = None


class DraftExecute(BaseModel):
    holding_id: Optional[int] = None
    discipline_checklist: Optional[dict] = None
    auto_create_holding: bool = False
    buy_price: Optional[float] = None
    """Broker-reported fill price. When provided with quantity, a Trade is recorded."""
    quantity: Optional[int] = None
    """Broker-reported fill quantity. When provided with buy_price, a Trade is recorded."""
