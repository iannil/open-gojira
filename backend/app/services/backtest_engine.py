"""Backtest engine — day-by-day strategy replay on historical data.

Loads BacktestRun.config, iterates trading days in range, builds
point-in-time context per stock, evaluates production strategies via
strategy_engine, simulates fills, records daily portfolio value.
On completion, computes metrics and stores in BacktestRun.result_json.

Config format:
{
  "stock_codes": list[str],          # universe
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "initial_capital": float,          # default 1_000_000
  "slippage_bps": int,               # default 10
  "strategies": list[int],           # strategy IDs to filter with (AND across strategies)
  "target_pct": float,               # per-BUY fraction of cash, default 0.10
}

Semantics:
- For each (day, stock): evaluate all strategies (AND-wise).
- All strategies pass AND not held → BUY target_pct of cash.
- Any strategy fails AND held → SELL entire position.
- Otherwise hold.

v1 simplifications (still apply):
- Single position per stock (no pyramiding).
- No shorting.
- Lixinger data must already be in historical_* tables.

Derived field availability in `build_stock_context_at` (point_in_time_context_service):
- pe_pct_10y / pb_pct_10y: ✅ computed via 10y window percentile (requires
  ≥30 samples in historical_valuations, else None)
- price_drop_pct: ✅ computed from 52w high in historical_klines
- ocf_to_ni: ✅ from latest historical_financials PUBLISHED ≤ day
  (point-in-time correct; None before first financial report)
- dividend_sustainability: ✅ PIT version (3/4 factors of production algo).
  OCF/NI + 分红连击 + DYR 比较 派息率趋势跳过 (HistoricalFinancial 无 payout_ratio 列)。
  Max 80 分而非 100 — strategies with high thresholds proportionally harder.

A 0-trade backtest is therefore usually CORRECT behavior (the stock didn't
match the strategy), not a bug. Verify by inspecting `build_stock_context_at`
output for the stock at a sample day.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import HTTPException
from app.core.datetime_utils import now
from sqlalchemy import distinct, select
from sqlalchemy.orm import Session

from app.models.backtest_run import BacktestRun
from app.models.broker_fee_config import BrokerFeeConfig
from app.models.corp_action import CorpAction
from app.models.historical_kline import HistoricalKline
from app.models.strategy import Strategy
from app.schemas.strategy import StrategyRule
from app.services.backtest_metrics import compute_all_metrics
from app.services.backtest_simulator import (
    PortfolioState, simulate_buy, simulate_sell,
    apply_dividend, apply_stock_dividend, apply_capitalization,
)
from app.services.point_in_time_context_service import (
    build_context_at, build_stock_context_at,
)
from app.services.strategy_engine import evaluate as strategy_evaluate


logger = logging.getLogger(__name__)


def _utcnow_naive() -> datetime:
    return now()


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


def _load_strategies(db: Session, strategy_ids: list[int]) -> list[Strategy]:
    """Load Strategy rows by ID, parsed rule_json cached on attribute."""
    if not strategy_ids:
        return []
    rows = db.execute(
        select(Strategy).where(Strategy.id.in_(strategy_ids))
    ).scalars().all()
    return list(rows)


def _evaluate_strategies(
    db: Session,
    strategies: list[Strategy],
    code: str,
    day: date,
) -> bool:
    """Evaluate all strategies AND-wise against a single stock on a single day.

    Returns True iff all strategies pass. Strategies with missing data
    fields return condition_results with passed=False → strategy fails →
    AND over strategies returns False.
    """
    if not strategies:
        return False  # No strategies = no signals (avoids accidental all-buy)
    ctx = build_stock_context_at(db, code, day)
    for s in strategies:
        try:
            rule = StrategyRule.model_validate_json(s.rule_json)
        except Exception:
            logger.warning(
                "Strategy %s has invalid rule_json; treating as fail", s.id
            )
            return False
        result = strategy_evaluate(rule, ctx)
        if not result.passed:
            return False
    return True


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
    target_pct: float,
) -> None:
    """Sizing + simulate_buy for a BUY signal (target_pct of cash)."""
    if code in portfolio.positions:
        return  # single position per stock, no pyramiding
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
    """SELL entire position."""
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
        target_pct = float(config.get("target_pct", 0.10))
        strategy_ids: list[int] = list(config.get("strategies", []))

        strategies = _load_strategies(db, strategy_ids)
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
            _apply_corp_actions_for_day(db, portfolio, day, stock_codes)

            # Evaluate strategies per stock
            for code in stock_codes:
                ctx = build_context_at(db, code, day)
                if not ctx.kline:
                    continue  # no trading that day

                all_passed = _evaluate_strategies(db, strategies, code, day)

                if all_passed and code not in portfolio.positions:
                    _execute_signal_buy(
                        portfolio=portfolio, code=code, ctx=ctx,
                        broker_cfg=broker_cfg, slippage_bps=slippage_bps,
                        day=day, target_pct=target_pct,
                    )
                elif not all_passed and code in portfolio.positions:
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
