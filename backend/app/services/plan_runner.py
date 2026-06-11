"""Plan runner — executes screening + optional trading evaluation.

For each active plan:
1. Resolve scan scope → list of stock codes
2. Build StockContext for each stock
3. Evaluate each strategy in the plan's composition
4. Update candidate pool (upsert active / mark removed)
5. For candidates in watchlist with trading rules: evaluate and emit drafts
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.candidate import Candidate
from app.models.plan import Plan
from app.models.stock import Stock
from app.models.strategy import Strategy
from app.models.watchlist import WatchlistItem
from app.services import draft_service
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
    return []


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


def _get_watchlisted_codes(db: Session) -> set[str]:
    """Get set of all stock codes currently in any watchlist group."""
    return {
        r[0] for r in db.execute(select(WatchlistItem.stock_code).distinct()).all()
    }


def _evaluate_trading_rules(
    db: Session,
    plan: Plan,
    stock_code: str,
    ctx,
) -> list:
    """Evaluate trading rules for a watchlisted candidate. Returns draft intents."""
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
        if trig.kind == "dyr_ge" and ctx.dyr is not None:
            triggered = ctx.dyr >= trig.value
        elif trig.kind == "pe_pct_le" and ctx.pe_pct_10y is not None:
            triggered = ctx.pe_pct_10y <= trig.value
        elif trig.kind == "price_le" and ctx.price is not None:
            triggered = ctx.price <= trig.value
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
                    triggered = drawdown <= -trig.value

        if triggered:
            drafts.append(("BUY", "buy_ladder", i, step.add_pct, None,
                          f"{trig.kind} triggered: {ctx.dyr if trig.kind == 'dyr_ge' else ctx.pe_pct_10y if trig.kind == 'pe_pct_le' else ctx.price} vs {trig.value}"))

    for i, step in enumerate(rules.sell_ladder):
        trig = step.trigger
        triggered = False
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
                    triggered = profit_pct >= trig.value
        elif trig.kind == "dyr_le" and ctx.dyr is not None:
            triggered = ctx.dyr <= trig.value
        elif trig.kind == "pe_pct_ge" and ctx.pe_pct_10y is not None:
            triggered = ctx.pe_pct_10y >= trig.value

        if triggered:
            drafts.append(("SELL", "sell_ladder", i, None, step.reduce_pct_of_position,
                          f"{trig.kind} triggered"))

    return drafts


def run_plan(db: Session, plan: Plan) -> PlanRunResult:
    """Run a single plan: scan scope → evaluate strategies → update candidates."""
    result = PlanRunResult(plan_id=plan.id, plan_name=plan.name)

    # 1. Resolve scope
    try:
        codes = _resolve_scope(db, plan)
    except Exception as e:
        result.errors.append(f"scope resolution failed: {e}")
        return result
    result.scanned = len(codes)

    if not codes:
        return result

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
    watchlisted = _get_watchlisted_codes(db)
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

    # 5. Trading rules for watchlisted candidates
    if plan.trading_rules_json:
        for code in passed_codes:
            if code not in watchlisted:
                continue
            try:
                ctx = build_context(db, code)
                intents = _evaluate_trading_rules(db, plan, code, ctx)
                for side, step_kind, step_index, add_pct, reduce_pct, reason in intents:
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
                    )
                    if draft:
                        result.drafts_emitted += 1
            except Exception as e:
                result.errors.append(f"trading eval failed for {code}: {e}")

    # 6. Update run summary
    plan.last_run_at = now
    plan.last_run_summary = json.dumps({
        "scanned": result.scanned,
        "passed": result.passed,
        "removed": result.removed,
        "new": result.new,
        "drafts": result.drafts_emitted,
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
