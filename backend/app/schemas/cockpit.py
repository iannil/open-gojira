"""Response schemas for the cockpit aggregator endpoint."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class CockpitCashflow(BaseModel):
    annual_expense: Optional[float] = None
    goal_multiple: Optional[float] = None
    target_annual_cashflow: Optional[float] = None
    weighted_dyr: Optional[float] = None
    annual_passive_cashflow: Optional[float] = None
    goal_progress: Optional[float] = None
    total_portfolio_value: Optional[float] = None
    currency: Optional[str] = None


class CockpitDraft(BaseModel):
    id: int
    plan_id: Optional[int] = None
    """M4 (Batch 5): nullable for thesis_breach SELL drafts (system-generated, no plan)."""
    code: str
    stock_name: Optional[str] = None
    side: str
    status: str
    step_kind: Optional[str] = None
    step_index: Optional[int] = None
    add_pct: Optional[float] = None
    reduce_pct_of_position: Optional[float] = None
    suggested_quantity: Optional[int] = None
    qiu_score: Optional[int] = None
    reason: Optional[str] = None
    source: Optional[str] = None
    triggered_at: Optional[str] = None


class CockpitHoldingItem(BaseModel):
    id: int
    stock_code: str
    stock_name: Optional[str] = None
    stock_industry: Optional[str] = None
    stock_tier: Optional[str] = None
    buy_date: Optional[str] = None
    buy_price: Optional[float] = None
    quantity: Optional[float] = None
    current_value: Optional[float] = None
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    annualized_return_pct: Optional[float] = None
    weight_pct: Optional[float] = None
    stop_profit_price: Optional[float] = None


class CockpitHoldings(BaseModel):
    items: list[CockpitHoldingItem] = []
    warnings: list[str] = []
    summary: Optional[dict[str, Any]] = None


class CockpitQuadrantItem(BaseModel):
    model_config = {"extra": "allow"}
    quadrant: Optional[str] = None


class CockpitAlertItem(BaseModel):
    id: int
    rule_id: Optional[int] = None
    stock_code: Optional[str] = None
    level: Optional[str] = None
    message: Optional[str] = None
    triggered_at: Optional[str] = None


class CockpitAlerts(BaseModel):
    items: list[CockpitAlertItem] = []
    unacked_count: int = 0


class CockpitPlan(BaseModel):
    id: int
    slug: Optional[str] = None
    name: str
    status: str
    description: Optional[str] = None
    is_builtin: Optional[bool] = None
    cycle_buy_max: Optional[str] = "mid"
    disable_midstream_filter: bool = False
    disable_in_circle_filter: bool = False
    """M2 (Batch 5): escape hatch for能力圈过滤."""
    last_run_at: Optional[str] = None
    last_run_summary: Optional[dict[str, Any]] = None
    """G1/G2/M2 feedback: keys include filtered_midstream_non_leader,
    filtered_out_of_circle, cycle_buy_blocked, cycle_unavailable_skipped,
    cycle_position, passed, scanned, drafts_emitted."""


class CockpitResponse(BaseModel):
    as_of: str
    cashflow: CockpitCashflow = CockpitCashflow()
    drafts: list[CockpitDraft] = []
    holdings: CockpitHoldings = CockpitHoldings()
    quadrant: list[dict[str, Any]] = []
    alerts: CockpitAlerts = CockpitAlerts()
    plans: list[CockpitPlan] = []
    theme_exposure: list[dict[str, Any]] = []
    rebalance_suggestions: list[dict[str, Any]] = []
    cycle: Optional[dict[str, Any]] = None
    cycle_banner: Optional[dict[str, Any]] = None
    """M3 (Batch 5): invest2 §5 逆向仓位法 — extreme_low/extreme_high 非阻塞 banner."""
    dividend_projection: Optional[dict[str, Any]] = None
    thesis_alerts: list[dict[str, Any]] = []
    portfolio_risk: Optional[dict[str, Any]] = None
    """D4: invest2 §7 平方差魔咒实时指标."""
    psychology_alerts: list[dict[str, Any]] = []
    """M1 (Batch 5): invest1 §13 回本强迫症嫌疑检测."""
    serenity_summary: Optional[dict[str, Any]] = None
    serenity_monthly_spend_cny: Optional[dict[str, Any]] = None
    errors: list[str] = []
