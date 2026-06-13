"""Backtest engine — day-by-day strategy replay on historical data.

Loads BacktestRun.config, iterates trading days in range, builds
point-in-time context per stock, evaluates strategy rules, simulates
fills, records daily portfolio value. On completion, computes metrics
and stores in BacktestRun.result_json.

Strategy rules format (simplified for v1):
[
    {"metric": "pe_ttm"|"pb"|"dyr"|"sp",
     "operator": "<"|">"|"<="|">=",
     "threshold": number,
     "action": "BUY"|"SELL",
     "target_pct": float  # for BUY, fraction of NAV to use
    },
    ...
]

v1 limitations (documented, not bugs):
- Single stock at a time per signal (no portfolio-level constraints)
- No shorting (SELL only if held)
- Strategy rules evaluated independently (AND/OR not supported in v1)
- Lixinger data must already be in historical_* tables (S4B.2)
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import distinct, select
from sqlalchemy.orm import Session

from app.models.backtest_run import BacktestRun
from app.models.broker_fee_config import BrokerFeeConfig
from app.models.corp_action import CorpAction
from app.models.historical_kline import HistoricalKline
from app.services.backtest_metrics import compute_all_metrics
from app.services.backtest_simulator import (
    PortfolioState, simulate_buy, simulate_sell,
    apply_dividend, apply_stock_dividend, apply_capitalization,
)
from app.services.point_in_time_context_service import build_context_at


logger = logging.getLogger(__name__)


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _get_trading_days(db: Session, start: date, end: date) -> list[date]:
    """Distinct dates in historical_klines within range, sorted."""
    rows = db.execute(
        select(distinct(HistoricalKline.date))
        .where(
            HistoricalKline.date >= start,
            HistoricalKline.date <= end,
        )
        .order_by(HistoricalKline.date)
    ).scalars().all()
    return list(rows)


def _get_active_fee_config(db: Session) -> BrokerFeeConfig:
    cfg = db.execute(
        select(BrokerFeeConfig)
        .where(BrokerFeeConfig.is_active == True)  # noqa: E712
        .order_by(BrokerFeeConfig.effective_from.desc())
        .limit(1)
    ).scalar_one_or_none()
    if not cfg:
        raise RuntimeError("No active broker_fee_config")
    return cfg


def _resolve_metric(metric: str, ctx) -> Optional[float]:
    """Pull metric value from point-in-time context."""
    if not ctx.valuation:
        return None
    return {
        "pe_ttm": ctx.valuation.pe_ttm,
        "pb": ctx.valuation.pb,
        "ps_ttm": ctx.valuation.ps_ttm,
        "dyr": ctx.valuation.dyr,
        "sp": ctx.valuation.sp,
        "mc": ctx.valuation.mc,
    }.get(metric)


_OPERATORS = {
    "<": lambda a, b: a < b,
    ">": lambda a, b: a > b,
    "<=": lambda a, b: a <= b,
    ">=": lambda a, b: a >= b,
    "==": lambda a, b: a == b,
}


def _evaluate_rule(rule: dict, ctx) -> Optional[str]:
    """Return 'BUY' / 'SELL' / None based on rule vs context.

    ctx is PointInTimeContext with .valuation, .financial, .kline.
    Returns None when any field is missing or operator unknown.
    """
    metric = rule.get("metric")
    operator = rule.get("operator")
    threshold = rule.get("threshold")
    action = rule.get("action")

    if not all([metric, operator, threshold is not None, action]):
        return None

    value = _resolve_metric(metric, ctx)
    if value is None:
        return None

    fn = _OPERATORS.get(operator)
    if not fn:
        return None
    if fn(value, threshold):
        return action
    return None


def _apply_corp_actions_for_day(
    db: Session, portfolio: PortfolioState, day: date, stock_codes: list[str]
) -> None:
    """Apply any corp_actions with ex_date == day for held positions."""
    if not stock_codes:
        return
    actions = db.execute(
        select(CorpAction).where(
            CorpAction.ex_date == day,
            CorpAction.stock_code.in_(stock_codes),
            CorpAction.processed_at.is_(None),
        )
    ).scalars().all()
    for action in actions:
        if action.stock_code not in portfolio.positions:
            continue
        if action.action_type == "cash_dividend":
            per_share = float(action.params_json.get("per_share", 0))
            apply_dividend(portfolio, action.stock_code, per_share)
        elif action.action_type == "stock_dividend":
            per_10 = float(action.params_json.get("per_10_shares", 0))
            apply_stock_dividend(portfolio, action.stock_code, per_10)
        elif action.action_type == "capitalization":
            per_10 = float(action.params_json.get("per_10_shares", 0))
            apply_capitalization(portfolio, action.stock_code, per_10)


def _compute_portfolio_value(
    portfolio: PortfolioState, db: Session, day: date
) -> float:
    """Cash + Σ(position_qty × current_close)."""
    total = portfolio.cash
    for code, pos in portfolio.positions.items():
        kline = db.execute(
            select(HistoricalKline).where(
                HistoricalKline.stock_code == code,
                HistoricalKline.date == day,
            )
        ).scalar_one_or_none()
        if kline:
            total += pos.quantity * kline.close
    return total


def _execute_signal_buy(
    *,
    portfolio: PortfolioState,
    code: str,
    ctx,
    broker_cfg: BrokerFeeConfig,
    slippage_bps: int,
    day: date,
    rule: dict,
) -> None:
    """Sizing + simulate_buy for a BUY signal (v1: target_pct of cash)."""
    if code in portfolio.positions:
        return  # v1: single position per stock, no pyramiding
    target_pct = float(rule.get("target_pct", 0.10))
    target_cash = portfolio.cash * target_pct
    close = ctx.kline.close
    if close <= 0:
        return
    raw_qty = int(target_cash // close)
    if raw_qty < 100:
        return  # below 1 lot
    simulate_buy(
        portfolio=portfolio, stock_code=code,
        target_price=close, quantity=raw_qty,
        kline={"low": ctx.kline.low, "high": ctx.kline.high},
        broker_config=broker_cfg,
        slippage_bps=slippage_bps,
        today=day,
    )


def _execute_signal_sell(
    *,
    portfolio: PortfolioState,
    code: str,
    ctx,
    broker_cfg: BrokerFeeConfig,
    slippage_bps: int,
    day: date,
) -> None:
    """SELL entire position (v1 simplification)."""
    pos = portfolio.positions.get(code)
    if not pos or pos.quantity <= 0:
        return
    simulate_sell(
        portfolio=portfolio, stock_code=code,
        target_price=ctx.kline.close, quantity=pos.quantity,
        kline={"low": ctx.kline.low, "high": ctx.kline.high},
        broker_config=broker_cfg,
        slippage_bps=slippage_bps,
        today=day,
    )


def run_backtest(db: Session, run_id: int) -> BacktestRun:
    """Execute a backtest. Updates BacktestRun in place.

    Raises HTTPException(404) when run_id unknown. Any exception during
    execution marks the run as failed (status=failed + error_message)
    and re-raises so callers can also see the error.
    """
    run = db.get(BacktestRun, run_id)
    if not run:
        raise HTTPException(404, f"BacktestRun {run_id} not found")

    config = run.config_json or {}
    run.status = "running"
    run.started_at = _utcnow_naive()
    run.error_message = None
    db.flush()

    try:
        stock_codes: list[str] = list(config.get("stock_codes", []))
        start = datetime.strptime(config["start_date"], "%Y-%m-%d").date()
        end = datetime.strptime(config["end_date"], "%Y-%m-%d").date()
        initial_capital = float(config.get("initial_capital", 1000000))
        slippage_bps = int(config.get("slippage_bps", 10))
        rules: list[dict] = list(config.get("strategy_rules", []))

        broker_cfg = _get_active_fee_config(db)
        trading_days = _get_trading_days(db, start, end)
        if not trading_days:
            run.status = "failed"
            run.error_message = "No historical data in range"
            run.completed_at = _utcnow_naive()
            db.flush()
            return run

        portfolio = PortfolioState(cash=initial_capital)
        equity_curve: list[dict] = []
        daily_returns: list[float] = []
        prev_value = initial_capital

        for day in trading_days:
            # Apply corp_actions for the day (before evaluating).
            # Affects held positions (cash in, share count, cost basis).
            _apply_corp_actions_for_day(db, portfolio, day, stock_codes)

            # Evaluate rules per stock
            for code in stock_codes:
                ctx = build_context_at(db, code, day)
                if not ctx.kline:
                    continue  # no trading that day

                for rule in rules:
                    signal = _evaluate_rule(rule, ctx)
                    if signal == "BUY":
                        _execute_signal_buy(
                            portfolio=portfolio, code=code, ctx=ctx,
                            broker_cfg=broker_cfg, slippage_bps=slippage_bps,
                            day=day, rule=rule,
                        )
                    elif signal == "SELL":
                        _execute_signal_sell(
                            portfolio=portfolio, code=code, ctx=ctx,
                            broker_cfg=broker_cfg, slippage_bps=slippage_bps,
                            day=day,
                        )

            # End-of-day portfolio value (cash + positions × close).
            value = _compute_portfolio_value(portfolio, db, day)
            equity_curve.append({"date": day.isoformat(), "value": value})
            if prev_value > 0:
                daily_returns.append((value - prev_value) / prev_value)
            prev_value = value

        # Compute metrics
        daily_values_tuples = [
            (datetime.strptime(p["date"], "%Y-%m-%d").date(), p["value"])
            for p in equity_curve
        ]
        metrics = compute_all_metrics(
            daily_values=daily_values_tuples,
            daily_returns=daily_returns,
            trades=portfolio.trades_log,
        )

        run.status = "completed"
        run.completed_at = _utcnow_naive()
        run.result_json = {
            "metrics": {
                "cagr": metrics.cagr,
                "total_return": metrics.total_return,
                "sharpe": metrics.sharpe,
                "max_drawdown": metrics.max_drawdown,
                "win_rate": metrics.win_rate,
                "avg_win": metrics.avg_win,
                "avg_loss": metrics.avg_loss,
                "trade_count": metrics.trade_count,
                "benchmark_return": metrics.benchmark_return,
                "alpha": metrics.alpha,
            },
            "equity_curve": equity_curve,
            "monthly_returns": metrics.monthly_returns,
            "trades_log": portfolio.trades_log,
            "final_cash": portfolio.cash,
            "final_positions": {
                code: {"quantity": pos.quantity, "avg_cost": pos.avg_cost}
                for code, pos in portfolio.positions.items()
            },
        }
        db.flush()
        return run

    except Exception as e:
        logger.exception("Backtest %s failed", run_id)
        # Roll back pending changes but keep the run record around so we
        # can mark it failed. The transaction state is caller's concern;
        # we use savepoint-ish semantics via a fresh get.
        try:
            db.rollback()
        except Exception:
            pass
        run = db.get(BacktestRun, run_id)
        if run:
            run.status = "failed"
            run.error_message = f"{type(e).__name__}: {str(e)[:500]}"
            run.completed_at = _utcnow_naive()
            db.flush()
        raise
