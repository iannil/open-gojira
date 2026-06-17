"""Plan runner — executes screening + optional trading evaluation.

For each active plan:
1. Resolve scan scope → list of stock codes
2. Build StockContext for each stock
3. Evaluate each strategy in the plan's composition
4. Update candidate pool (upsert active / mark removed)
5. For all candidates with trading rules: evaluate and emit drafts

Note (重审 2026-06-13 #1+#4): the watchlist promotion gate was removed.
Previously only candidates manually promoted to a watchlist would have their
trading rules evaluated; this silently filtered 296 real candidates → 0 drafts.
Trading rules now evaluate for every stock that passes the screening strategies.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.broker_fee_config import BrokerFeeConfig
from app.models.candidate import Candidate
from app.models.cash_balance import CashBalance
from app.models.draft import Draft
from app.models.plan import Plan
from app.models.stock import Stock
from app.models.strategy import Strategy
from app.models.trade import Trade
from app.models.watchlist import WatchlistItem
from app.services import draft_service
from app.services.holding_view_service import available_quantity_at
from app.services.position_sizing_service import compute_buy_quantity
from app.services.price_validator_service import is_suspended
from app.services.stock_context_builder import build_context, build_screening_contexts
from app.services.strategy_engine import StockContext
from app.services.strategy_engine import evaluate as strategy_evaluate
from app.services.strategy_engine import _resolve_field as resolve_field, _evaluate_condition

from app.core.events import bus, PlanEvaluationCompleted

try:
    from app.core.observability import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


@dataclass
class PlanRunResult:
    plan_id: int
    plan_name: str
    scanned: int = 0
    passed: int = 0
    removed: int = 0
    new: int = 0
    drafts_emitted: int = 0
    drafts_superseded: int = 0
    """Count of previously-pending drafts marked 'superseded' this run.
    A draft is superseded when its (plan, code, step) wasn't re-confirmed
    by the current run — either the stock dropped out of candidates or
    trading rules no longer fire."""
    filtered_midstream_non_leader: int = 0
    filtered_red_flags: int = 0
    """D3 (2026-06-17): count of candidates suppressed by red_flag_count > 0
    (invest1 §三 + invest2 §10 财报避坑)."""
    cycle_position: str | None = None
    """G1: current cycle position when plan ran (extreme_low/low/mid/high/extreme_high)."""
    cycle_buy_blocked: int = 0
    """G1: count of BUY drafts suppressed by cycle gate (current_rank > plan.cycle_buy_max)."""
    cycle_unavailable_skipped: bool = False
    """G1: True if plan run was skipped entirely because cycle data was unavailable."""
    errors: list[str] = field(default_factory=list)


def _resolve_scope(db: Session, plan: Plan) -> list[str]:
    """Resolve scan scope to a list of stock codes."""
    from app.schemas.plan import ScanScope
    scope = ScanScope.model_validate_json(plan.scan_scope_json)

    if scope.type == "all_stocks":
        return list(db.execute(
            select(Stock.code).where(Stock.delisted_at.is_(None))
        ).scalars().all())
    elif scope.type == "industries":
        return list(db.execute(
            select(Stock.code).where(Stock.industry.in_(scope.values))
        ).scalars().all())
    elif scope.type == "index":
        logger.warning(
            "index scope requested but not implemented; falling back to all_stocks. "
            "plan_id=%s scope_values=%s",
            plan.id, scope.values,
        )
        return list(db.execute(
            select(Stock.code).where(Stock.delisted_at.is_(None))
        ).scalars().all())
    elif scope.type == "watchlist":
        return list(db.execute(
            select(WatchlistItem.stock_code).where(
                WatchlistItem.group_id.in_([int(v) for v in scope.values])
            )
        ).scalars().all())
    elif scope.type == "custom":
        return scope.values
    elif scope.type == "business_pattern":
        # C2: 按 BusinessPattern 圈定扫描范围。values 是 pattern ID 字符串。
        try:
            pattern_ids = [int(v) for v in scope.values]
        except ValueError as e:
            raise ValueError(
                f"business_pattern scope values must be integers: {scope.values}"
            ) from e
        return list(db.execute(
            select(Stock.code).where(
                Stock.business_pattern_id.in_(pattern_ids),
                Stock.delisted_at.is_(None),
            )
        ).scalars().all())
    return []


def _should_filter_as_midstream_non_leader(
    db: Session, stock: Stock, plan: Plan
) -> bool:
    """G2 (invest3 §13): filter midstream non-cost-leader stocks.

    Rule: if stock's BusinessPattern.is_midstream=True AND stock.is_cost_leader
    is not strictly True → filter (剔除). This implements the文档硬规则
    "中游企业一般不要投资，除非它是成本最低的那个".

    Bypass conditions:
    - plan.disable_midstream_filter=True → never filter
    - stock has no business_pattern_id → cannot apply (keep)
    - pattern.is_midstream=False → not midstream (keep)

    Returns True if stock should be filtered out.
    """
    if plan.disable_midstream_filter:
        return False
    if stock.business_pattern_id is None:
        return False
    from app.models.business_pattern import BusinessPattern
    pattern = db.get(BusinessPattern, stock.business_pattern_id)
    if pattern is None or not pattern.is_midstream:
        return False
    return stock.is_cost_leader is not True


# ── G1 cycle gate (invest3 §5) ────────────────────────────────────────
# 5 cycle positions (rank 升序 = 越来越高估):
_CYCLE_POSITION_RANKS = {
    "extreme_low": 0,
    "low": 1,
    "mid": 2,
    "high": 3,
    "extreme_high": 4,
}


def _cycle_position_rank(pos: str) -> int:
    """Convert cycle position string to ordinal rank (0=most undervalued)."""
    if pos not in _CYCLE_POSITION_RANKS:
        raise ValueError(f"unknown cycle position: {pos!r}")
    return _CYCLE_POSITION_RANKS[pos]


def _check_cycle_gate(plan_max: str, current: str) -> bool:
    """G1 (invest3 §5): should BUY drafts be blocked?

    Returns True if current cycle rank > plan.cycle_buy_max rank — meaning
    market is too hot and new buys should be suppressed. SELL drafts are
    unaffected (cycle=high may legitimately trigger take-profit).
    """
    return _cycle_position_rank(current) > _cycle_position_rank(plan_max)


def _strategy_definitely_fails(rule, ctx: StockContext) -> bool:
    """Check if a strategy definitely fails given available context data.

    For AND logic: returns True if any available condition fails (fail-fast).
    For OR logic: returns True only if ALL available conditions fail AND no unavailable fields remain.
    Returns False if we can't determine (all fields unavailable) or stock may pass.
    """
    available_results = []
    has_unavailable = False

    for cond in rule.conditions:
        actual = resolve_field(ctx, cond.field)
        if actual is None:
            has_unavailable = True
            continue
        cond_result = _evaluate_condition(cond, ctx)
        available_results.append(cond_result.passed)

    if not available_results:
        return False

    if rule.logic == "OR":
        if any(available_results):
            return False
        return not has_unavailable
    else:
        return not all(available_results)


def _evaluate_strategies(
    strategies: list[Strategy], ctx: StockContext, comp,
) -> tuple[dict, bool]:
    """Evaluate all strategies and return (strategy_results, passed)."""
    from app.schemas.strategy import StrategyRule

    strategy_results = {}
    all_results = []
    for s in strategies:
        rule = StrategyRule.model_validate_json(s.rule_json)
        eval_result = strategy_evaluate(rule, ctx)
        strategy_results[s.id] = {
            "passed": eval_result.passed,
            "details": [r.detail for r in eval_result.condition_results],
        }
        all_results.append(eval_result.passed)

    if not all_results:
        return strategy_results, False
    if comp.logic == "AND":
        passed = all(all_results)
    else:
        passed = any(all_results)
    return strategy_results, passed


def _upsert_candidate(
    db: Session, plan: Plan, code: str,
    strategy_results: dict, result: PlanRunResult,
) -> None:
    """Insert or update a candidate record."""
    existing = db.execute(
        select(Candidate).where(
            Candidate.plan_id == plan.id,
            Candidate.stock_code == code,
            Candidate.status == "active",
        )
    ).scalar_one_or_none()

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if existing:
        existing.last_confirmed_at = now
        existing.last_eval_json = json.dumps(strategy_results)
    else:
        candidate = Candidate(
            plan_id=plan.id,
            stock_code=code,
            status="active",
            last_eval_json=json.dumps(strategy_results),
        )
        db.add(candidate)
        result.new += 1


def _filter_suspended(db: Session, codes: list[str]) -> list[str]:
    """Drop codes whose Stock.listing_status marks them as suspended.

    Suspended statuses (ipo_suspension / delisting_transitional_period /
    issued_but_not_listed / issue_failure / unauthorized) cannot be traded,
    so they are excluded from the scan entirely — saves context building +
    evaluation cost for stocks that could never produce a useful Draft.
    """
    if not codes:
        return []
    rows = db.execute(
        select(Stock.code, Stock.listing_status).where(Stock.code.in_(codes))
    ).all()
    return [r.code for r in rows if not is_suspended(r.listing_status)]


def _get_active_fee_config(
    db: Session, moment: datetime
) -> BrokerFeeConfig | None:
    """Pick the most recent active broker_fee_config effective as of `moment`.

    Returns None when no config exists — callers should treat None as
    'skip BUY sizing' (suggested_quantity stays None).
    """
    return db.execute(
        select(BrokerFeeConfig)
        .where(
            BrokerFeeConfig.is_active == True,  # noqa: E712
            BrokerFeeConfig.effective_from <= moment.date(),
        )
        .order_by(BrokerFeeConfig.effective_from.desc())
        .limit(1)
    ).scalar_one_or_none()


def _holdings_market_value(db: Session) -> float:
    """Approximate current market value of open positions.

    For each open stock_code, sum Trade.quantity (signed: BUY +N, SELL −N)
    and multiply by Stock.prev_close as the latest price proxy. Used as
    the NAV addend when computing BUY quantity.
    """
    from sqlalchemy import func as sa_func
    agg = db.execute(
        select(Trade.stock_code, sa_func.sum(Trade.quantity))
        .where(Trade.reversed_by_trade_id.is_(None))
        .group_by(Trade.stock_code)
    ).all()
    if not agg:
        return 0.0
    codes = [r[0] for r in agg]
    prices = {
        r.code: (r.prev_close or 0.0)
        for r in db.execute(
            select(Stock.code, Stock.prev_close).where(Stock.code.in_(codes))
        ).all()
    }
    total = 0.0
    for stock_code, qty in agg:
        q = int(qty or 0)
        if q <= 0:
            continue
        total += q * prices.get(stock_code, 0.0)
    return total


def _compute_suggested_buy_quantity(
    db: Session,
    *,
    code: str,
    prev_close: float | None,
    add_pct: float | None,
    moment: datetime,
) -> int | None:
    """Compute suggested BUY quantity for a draft via position_sizing_service.

    Returns None when inputs are insufficient (no prev_close / no add_pct /
    no fee config / cash balance missing) so the caller can skip populating
    the field without raising.
    """
    if not add_pct or add_pct <= 0:
        return None
    if not prev_close or prev_close <= 0:
        return None

    cfg = _get_active_fee_config(db, moment)
    if cfg is None:
        return None

    cb = db.execute(select(CashBalance).limit(1)).scalar_one_or_none()
    if cb is None:
        return None

    nav = float(cb.balance) + _holdings_market_value(db)
    if nav <= 0:
        return None

    try:
        result = compute_buy_quantity(
            capital_base=nav,
            target_pct=add_pct,
            current_price=float(prev_close),
            available_cash=float(cb.balance),
            broker_config=cfg,
        )
        return result.quantity or None
    except Exception:
        logger.exception(
            "position sizing failed for code=%s add_pct=%s", code, add_pct,
        )
        return None


def _format_buy_reason(trig_kind: str, actual: float | None, threshold: float) -> str:
    """Translate a buy-side trigger into a human-readable Chinese string.

    2026-06-13 验收补充: 原 "dyr_ge triggered: 0.061 vs 0.06" 改为
    "股息率 6.10% ≥ 阈值 6.00%",让用户看一眼就懂。
    """
    pct = lambda v: f"{v * 100:.2f}%" if v is not None else "—"
    pct1 = lambda v: f"{v * 100:.1f}%" if v is not None else "—"
    if trig_kind == "dyr_ge":
        return f"股息率 {pct(actual)} ≥ 阈值 {pct(threshold)}"
    if trig_kind == "dyr_fwd_ge":
        return f"预期股息率 {pct(actual)} ≥ 阈值 {pct(threshold)}"
    if trig_kind == "pe_pct_le":
        return f"PE 10年分位 {pct1(actual)} ≤ 阈值 {pct1(threshold)}"
    if trig_kind == "price_le":
        return f"现价 ¥{actual:.2f} ≤ 阈值 ¥{threshold:.2f}" if actual is not None else f"现价 — ≤ ¥{threshold:.2f}"
    if trig_kind == "drawdown_from_last_buy":
        return f"距上次买入回撤 {pct1(actual)} ≤ 阈值 -{pct1(threshold)}"
    return f"{trig_kind} triggered"


def _format_sell_reason(trig_kind: str, actual: float | None, threshold: float) -> str:
    """Translate a sell-side trigger into a human-readable Chinese string."""
    pct = lambda v: f"{v * 100:.2f}%" if v is not None else "—"
    pct1 = lambda v: f"{v * 100:.1f}%" if v is not None else "—"
    if trig_kind == "profit_pct_ge":
        return f"收益率 +{pct1(actual)} ≥ 止盈线 +{pct1(threshold)}"
    if trig_kind == "dyr_le":
        return f"股息率 {pct(actual)} ≤ 警戒线 {pct(threshold)}"
    if trig_kind == "dyr_fwd_le":
        return f"预期股息率 {pct(actual)} ≤ 警戒线 {pct(threshold)}"
    if trig_kind == "cycle_position_ge":
        return f"市场周期 {actual} ≥ 减仓阈值 {threshold}"
    if trig_kind == "pe_pct_ge":
        return f"PE 10年分位 {pct1(actual)} ≥ 阈值 {pct1(threshold)}"
    return f"{trig_kind} triggered"


def _evaluate_trading_rules(
    db: Session,
    plan: Plan,
    stock_code: str,
    ctx,
    cycle_position: str | None = None,
) -> list:
    """Evaluate trading rules for a watchlisted candidate. Returns draft intents.

    cycle_position: B1 (G1 v2) — current market cycle position, passed by
    run_plan caller so cycle_position_ge sell triggers can be evaluated.
    """
    from app.schemas.plan import TradingRules
    rules_json = plan.trading_rules_json
    if not rules_json:
        return []

    try:
        rules = TradingRules.model_validate_json(rules_json)
    except Exception:
        return []

    drafts = []
    for i, step in enumerate(rules.buy_ladder):
        trig = step.trigger
        triggered = False
        actual = None
        if trig.kind == "dyr_ge" and ctx.dyr is not None:
            triggered = ctx.dyr >= trig.value
            actual = ctx.dyr
        elif trig.kind == "dyr_fwd_ge" and ctx.forward_dyr is not None:
            triggered = ctx.forward_dyr >= trig.value
            actual = ctx.forward_dyr
        elif trig.kind == "pe_pct_le" and ctx.pe_pct_10y is not None:
            triggered = ctx.pe_pct_10y <= trig.value
            actual = ctx.pe_pct_10y
        elif trig.kind == "price_le" and ctx.price is not None:
            triggered = ctx.price <= trig.value
            actual = ctx.price
        elif trig.kind == "drawdown_from_last_buy":
            if ctx.price is not None:
                from app.models.holding import Holding
                last_buy = db.execute(
                    select(Holding).where(
                        Holding.stock_code == stock_code,
                        Holding.sell_date.is_(None),
                    ).order_by(Holding.buy_date.desc())
                ).scalars().first()
                if last_buy and last_buy.buy_price and last_buy.buy_price > 0:
                    drawdown = (ctx.price - float(last_buy.buy_price)) / float(last_buy.buy_price)
                    actual = drawdown
                    triggered = drawdown <= -trig.value

        if triggered:
            reason = _format_buy_reason(trig.kind, actual, trig.value)
            drafts.append(("BUY", "buy_ladder", i, step.add_pct, None, reason))

    for i, step in enumerate(rules.sell_ladder):
        trig = step.trigger
        triggered = False
        actual = None
        if trig.kind == "profit_pct_ge":
            if ctx.price is not None:
                from app.models.holding import Holding
                h = db.execute(
                    select(Holding).where(
                        Holding.stock_code == stock_code,
                        Holding.sell_date.is_(None),
                    )
                ).scalar_one_or_none()
                if h and h.buy_price and h.buy_price > 0:
                    profit_pct = (ctx.price - float(h.buy_price)) / float(h.buy_price)
                    actual = profit_pct
                    triggered = profit_pct >= trig.value
        elif trig.kind == "dyr_le" and ctx.dyr is not None:
            triggered = ctx.dyr <= trig.value
            actual = ctx.dyr
        elif trig.kind == "dyr_fwd_le" and ctx.forward_dyr is not None:
            triggered = ctx.forward_dyr <= trig.value
            actual = ctx.forward_dyr
        elif trig.kind == "pe_pct_ge" and ctx.pe_pct_10y is not None:
            triggered = ctx.pe_pct_10y >= trig.value
            actual = ctx.pe_pct_10y
        elif trig.kind == "cycle_position_ge":
            # B1 (G1 v2): invest3 §5 "高位主动减仓"
            if cycle_position is not None:
                current_rank = _cycle_position_rank(cycle_position)
                trigger_rank = _cycle_position_rank(str(trig.value))
                triggered = current_rank >= trigger_rank
                actual = cycle_position
            else:
                triggered = False

        if triggered:
            reason = _format_sell_reason(trig.kind, actual, trig.value)
            drafts.append(("SELL", "sell_ladder", i, None, step.reduce_pct_of_position, reason))

    return drafts


def run_plan(db: Session, plan: Plan) -> PlanRunResult:
    """Run a single plan: scan scope → evaluate strategies → update candidates."""
    # S3.5 — freshness gate. Refuse to run on stale data so we don't generate
    # phantom drafts from yesterday's prices / dividends. 48h tolerance covers
    # weekends and a single missed sync. Raises DataStaleError (HTTP 503) and
    # emits a system_alert so the UI can surface the failure.
    from app.services.data_freshness_service import assert_fresh_enough

    for _category in ("stocks", "valuation"):
        assert_fresh_enough(db, _category, max_age_hours=48)

    result = PlanRunResult(plan_id=plan.id, plan_name=plan.name)

    # G1 (Q10=C): cycle gate — if cycle data unavailable, skip entire plan run.
    # Rationale: per invest3 §5, market position must inform buy decisions;
    # without it, all drafts would be based on incomplete context.
    try:
        from app.services.cycle_assessment_service import assess_cycle
        cycle = assess_cycle(db)
        if cycle.pe_pct_10y is None:
            result.cycle_unavailable_skipped = True
            result.errors.append(
                "cycle_assessment data unavailable (pe_pct_10y is None) — "
                "plan run skipped per G1 fallback policy"
            )
            logger.warning(
                "Plan '%s' skipped: cycle_assessment data unavailable",
                plan.name,
            )
            return result
        result.cycle_position = cycle.cycle_position
    except Exception as e:
        result.cycle_unavailable_skipped = True
        result.errors.append(f"cycle_assessment failed: {e} — plan run skipped")
        logger.warning("Plan '%s' skipped: cycle_assessment error", plan.name, exc_info=True)
        return result

    # 1. Resolve scope
    try:
        codes = _resolve_scope(db, plan)
    except Exception as e:
        result.errors.append(f"scope resolution failed: {e}")
        return result
    result.scanned = len(codes)

    if not codes:
        return result

    # 1b. Filter out suspended stocks (S2.5) — they cannot be traded so they
    # should never enter the candidate pool or produce a Draft.
    codes = _filter_suspended(db, codes)

    # 2. Load strategies
    from app.schemas.plan import StrategyComposition
    comp = StrategyComposition.model_validate_json(plan.strategy_composition_json)
    strategies = []
    for sid in comp.strategy_ids:
        s = db.get(Strategy, sid)
        if s is None:
            result.errors.append(f"strategy {sid} not found")
            continue
        strategies.append(s)

    if not strategies:
        result.errors.append("no valid strategies")
        return result

    # 3. Build contexts and evaluate
    passed_codes = []

    # Use lightweight batch context for large scopes (>500 stocks)
    use_batch_screening = len(codes) > 500

    if use_batch_screening:
        # Two-pass evaluation for large scopes
        lightweight_contexts = build_screening_contexts(db, codes)

        # Pass 1: Fail-fast screening — eliminate stocks that definitely fail
        surviving_codes = []
        for code in codes:
            ctx = lightweight_contexts.get(code)
            if ctx is None:
                ctx = StockContext(code=code)

            eliminated = False
            for s in strategies:
                from app.schemas.strategy import StrategyRule
                rule = StrategyRule.model_validate_json(s.rule_json)
                if _strategy_definitely_fails(rule, ctx):
                    eliminated = True
                    break

            if not eliminated:
                surviving_codes.append(code)

        logger.info(
            "Pass 1 done for plan '%s': %d/%d stocks survived",
            plan.name, len(surviving_codes), len(codes),
        )

        # Pass 2: Full evaluation for surviving stocks
        for code in surviving_codes:
            try:
                ctx = build_context(db, code)
            except Exception as e:
                result.errors.append(f"context build failed for {code}: {e}")
                continue

            strategy_results, passed = _evaluate_strategies(strategies, ctx, comp)
            if not passed:
                continue

            # G2 midstream filter (invest3 §13)
            stock = db.get(Stock, code)
            if stock is not None and _should_filter_as_midstream_non_leader(db, stock, plan):
                result.filtered_midstream_non_leader += 1
                continue

            # D3 (2026-06-17): 财报红旗 filter (invest1 §三 + invest2 §10)
            if ctx.red_flag_count is not None and ctx.red_flag_count > 0:
                result.filtered_red_flags += 1
                continue

            passed_codes.append(code)
            _upsert_candidate(db, plan, code, strategy_results, result)
    else:
        # Small scope: per-stock full context building
        for code in codes:
            try:
                ctx = build_context(db, code)
            except Exception as e:
                result.errors.append(f"context build failed for {code}: {e}")
                continue

            strategy_results, passed = _evaluate_strategies(strategies, ctx, comp)
            if not passed:
                continue

            # G2 midstream filter (invest3 §13)
            stock = db.get(Stock, code)
            if stock is not None and _should_filter_as_midstream_non_leader(db, stock, plan):
                result.filtered_midstream_non_leader += 1
                continue

            # D3 (2026-06-17): 财报红旗 filter (invest1 §三 + invest2 §10)
            if ctx.red_flag_count is not None and ctx.red_flag_count > 0:
                result.filtered_red_flags += 1
                continue

            passed_codes.append(code)
            _upsert_candidate(db, plan, code, strategy_results, result)

    result.passed = len(passed_codes)

    # 4. Mark removed candidates (no longer passing)
    active_candidates = db.execute(
        select(Candidate).where(
            Candidate.plan_id == plan.id,
            Candidate.status == "active",
        )
    ).scalars().all()

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for c in active_candidates:
        if c.stock_code not in passed_codes and not c.pinned:
            c.status = "removed"
            c.removed_at = now
            result.removed += 1

    # 5. Trading rules for all passing candidates (重审 #1+#4: 闸门已删)
    # Track IDs of drafts emitted/refreshed this run so we can supersede
    # the rest. (D 分支 Q18 决策) — avoids unreliable timestamp comparison.
    emitted_draft_ids: set[int] = set()
    if plan.trading_rules_json:
        # G1 (Q8=A): cycle gate — block BUY drafts when market is too hot.
        # SELL drafts remain unaffected (cycle=high may legitimately trigger
        # take-profit). cycle_unavailable was already handled at plan start.
        cycle_blocks_buy = (
            result.cycle_position is not None
            and _check_cycle_gate(plan.cycle_buy_max, result.cycle_position)
        )
        if cycle_blocks_buy:
            logger.info(
                "Plan '%s': cycle gate active (cycle=%s, max=%s) — BUY drafts suppressed",
                plan.name, result.cycle_position, plan.cycle_buy_max,
            )
        eval_moment = datetime.now(timezone.utc).replace(tzinfo=None)
        for code in passed_codes:
            try:
                ctx = build_context(db, code)
                intents = _evaluate_trading_rules(
                    db, plan, code, ctx, cycle_position=result.cycle_position,
                )
                for side, step_kind, step_index, add_pct, reduce_pct, reason in intents:
                    # G1: cycle gate suppresses BUY side
                    if side == "BUY" and cycle_blocks_buy:
                        result.cycle_buy_blocked += 1
                        continue
                    # S2.5: SELL T+1 — if no settled shares are available,
                    # emitting a SELL draft would only produce noise.
                    if side == "SELL":
                        try:
                            available = available_quantity_at(
                                db, code, eval_moment,
                            )
                        except Exception:
                            available = 0
                        if available <= 0:
                            continue
                        suggested_qty = None
                    else:
                        # S2.5: BUY suggested_quantity — compute actual lot size.
                        stock = db.get(Stock, code)
                        prev_close = (
                            float(stock.prev_close) if stock and stock.prev_close else None
                        )
                        suggested_qty = _compute_suggested_buy_quantity(
                            db,
                            code=code,
                            prev_close=prev_close,
                            add_pct=add_pct,
                            moment=eval_moment,
                        )
                    draft = draft_service.emit(
                        db,
                        plan=plan,
                        stock_code=code,
                        side=side,
                        step_kind=step_kind,
                        step_index=step_index,
                        reason=reason,
                        add_pct=add_pct,
                        reduce_pct_of_position=reduce_pct,
                        suggested_quantity=suggested_qty,
                    )
                    if draft:
                        emitted_draft_ids.add(draft.id)
                        result.drafts_emitted += 1
            except Exception as e:
                result.errors.append(f"trading eval failed for {code}: {e}")

    # 5b. Auto-supersede stale drafts (D 分支 Q18 决策)
    # Any pending draft for this plan that wasn't emitted/refreshed this run
    # is stale — either the stock dropped out of candidates (no trading rule
    # evaluation) or trading rules no longer fire. Either way, the draft no
    # longer represents a current suggestion → supersede.
    now_supersede = datetime.now(timezone.utc).replace(tzinfo=None)
    pending_drafts = db.execute(
        select(Draft).where(
            Draft.plan_id == plan.id,
            Draft.status == "pending",
        )
    ).scalars().all()
    stale_drafts = [d for d in pending_drafts if d.id not in emitted_draft_ids]
    for d in stale_drafts:
        d.status = "superseded"
        d.executed_at = now_supersede
    if stale_drafts:
        logger.info(
            "Plan '%s': superseded %d stale drafts (not re-confirmed this run)",
            plan.name, len(stale_drafts),
        )
    result.drafts_superseded = len(stale_drafts)

    # 6. Update run summary
    plan.last_run_at = now
    plan.last_run_summary = json.dumps({
        "scanned": result.scanned,
        "passed": result.passed,
        "removed": result.removed,
        "new": result.new,
        "drafts": result.drafts_emitted,
        "drafts_superseded": result.drafts_superseded,
        "errors": result.errors[:10],
    })

    db.flush()
    return result


def run_all_active(db: Session) -> list[PlanRunResult]:
    """Run all active plans."""
    active = db.execute(
        select(Plan).where(Plan.status == "active")
    ).scalars().all()

    results = []
    for plan in active:
        try:
            r = run_plan(db, plan)
            results.append(r)
            try:
                bus.emit(PlanEvaluationCompleted(
                    plan_id=r.plan_id,
                    plan_name=r.plan_name,
                    scanned=r.scanned,
                    passed=r.passed,
                    drafts_emitted=r.drafts_emitted,
                    errors=len(r.errors),
                ))
            except Exception:
                logger.exception("EventBus emit PlanEvaluationCompleted failed for plan %d", r.plan_id)
        except Exception as e:
            results.append(PlanRunResult(
                plan_id=plan.id,
                plan_name=plan.name,
                errors=[f"plan run failed: {e}"],
            ))
            try:
                bus.emit(PlanEvaluationCompleted(
                    plan_id=plan.id,
                    plan_name=plan.name,
                    errors=1,
                ))
            except Exception:
                logger.exception("EventBus emit PlanEvaluationCompleted failed for plan %d", plan.id)

    return results
