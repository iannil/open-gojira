"""Backtest performance metrics — CAGR / Sharpe / MaxDD / win rate.

Pure functions on equity curves + trade logs. No DB / no side effects.
Used by S4C.4 backtest_engine to compute final metrics.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class BacktestMetrics:
    cagr: float
    """Compound annual growth rate (e.g. 0.15 = 15%/yr)."""
    total_return: float
    """(end - start) / start."""
    sharpe: float
    """Annualized Sharpe ratio (assumes 252 trading days)."""
    max_drawdown: float
    """Largest peak-to-trough decline (negative number, e.g. -0.20)."""
    win_rate: float
    """Fraction of all trades with positive realized_pnl
    (break-even trades count in the denominator but not as wins)."""
    avg_win: float
    avg_loss: float
    monthly_returns: dict[str, float]
    """YYYY-MM → return fraction."""
    benchmark_return: float | None = None
    alpha: float | None = None
    """Strategy return - benchmark return."""
    trade_count: int = 0


DAYS_PER_YEAR = 365.25
TRADING_DAYS_PER_YEAR = 252


def compute_cagr(
    start_value: float, end_value: float,
    start_date: date, end_date: date,
) -> float:
    """Compound annual growth rate.

    Returns -1.0 on total loss, 0.0 on zero-duration or non-positive start.
    """
    if start_value <= 0:
        return 0.0
    years = (end_date - start_date).days / DAYS_PER_YEAR
    if years <= 0:
        return 0.0
    if end_value <= 0:
        return -1.0  # total loss
    return (end_value / start_value) ** (1 / years) - 1


def compute_sharpe(
    daily_returns: list[float],
    risk_free_rate: float = 0.02,
) -> float:
    """Annualized Sharpe ratio.

    Uses daily risk-free = rf / 252 and std of excess returns,
    annualized via sqrt(252). Returns 0.0 if series is constant or too short.
    """
    if not daily_returns or len(daily_returns) < 2:
        return 0.0
    daily_rf = risk_free_rate / TRADING_DAYS_PER_YEAR
    excess = [r - daily_rf for r in daily_returns]
    mean_excess = statistics.mean(excess)
    std = statistics.stdev(excess)
    if std == 0:
        return 0.0
    return (mean_excess / std) * math.sqrt(TRADING_DAYS_PER_YEAR)


def compute_max_drawdown(equity_series: list[float]) -> float:
    """Largest peak-to-trough decline. Returns negative fraction or 0.0."""
    if not equity_series:
        return 0.0
    peak = equity_series[0]
    max_dd = 0.0
    for value in equity_series:
        if value > peak:
            peak = value
        if peak > 0:
            dd = (value - peak) / peak
            if dd < max_dd:
                max_dd = dd
    return max_dd


def compute_win_rate(trades: list[dict]) -> dict:
    """Win/loss stats from a trade log.

    win_rate = wins / total (break-even trades are in denominator but
    not counted as wins). avg_win / avg_loss averaged over winners/losers.
    """
    if not trades:
        return {
            "total": 0, "wins": 0, "losses": 0,
            "win_rate": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
        }
    wins = [t for t in trades if (t.get("realized_pnl") or 0) > 0]
    losses = [t for t in trades if (t.get("realized_pnl") or 0) < 0]
    total = len(trades)
    win_rate = len(wins) / total if total > 0 else 0.0
    avg_win = (
        statistics.mean([t["realized_pnl"] for t in wins]) if wins else 0.0
    )
    avg_loss = (
        statistics.mean([t["realized_pnl"] for t in losses]) if losses else 0.0
    )
    return {
        "total": total,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
    }


def compute_monthly_returns(
    daily_values: list[tuple[date, float]],
) -> dict[str, float]:
    """Per-month intra-month return.

    For each month: (last_value - first_value) / first_value, where
    first_value and last_value are the first and last observations
    within that calendar month. Months with only one observation are
    skipped (no intra-month change to measure).
    """
    if len(daily_values) < 2:
        return {}
    # Group by YYYY-MM
    by_month: dict[str, list[tuple[date, float]]] = {}
    for d, v in daily_values:
        key = d.strftime("%Y-%m")
        by_month.setdefault(key, []).append((d, v))
    monthly: dict[str, float] = {}
    for month, entries in sorted(by_month.items()):
        if len(entries) < 2:
            continue
        entries.sort(key=lambda x: x[0])
        first_v = entries[0][1]
        last_v = entries[-1][1]
        if first_v > 0:
            monthly[month] = (last_v - first_v) / first_v
    return monthly


def compute_all_metrics(
    *,
    daily_values: list[tuple[date, float]],
    daily_returns: list[float],
    trades: list[dict],
    risk_free_rate: float = 0.02,
    benchmark_series: list[tuple[date, float]] | None = None,
) -> BacktestMetrics:
    """Composite: assemble all metrics from raw series.

    Sorts inputs by date, computes each metric via the pure helpers, and
    derives alpha = strategy_return - benchmark_return when benchmark is
    provided.
    """
    if not daily_values:
        return BacktestMetrics(
            cagr=0.0, total_return=0.0, sharpe=0.0, max_drawdown=0.0,
            win_rate=0.0, avg_win=0.0, avg_loss=0.0,
            monthly_returns={}, trade_count=0,
        )

    sorted_values = sorted(daily_values, key=lambda x: x[0])
    start_d, start_v = sorted_values[0]
    end_d, end_v = sorted_values[-1]

    cagr = compute_cagr(start_v, end_v, start_d, end_d)
    total_return = (end_v - start_v) / start_v if start_v > 0 else 0.0
    sharpe = compute_sharpe(daily_returns, risk_free_rate)
    mdd = compute_max_drawdown([v for _, v in sorted_values])
    win_stats = compute_win_rate(trades)
    monthly = compute_monthly_returns(sorted_values)

    benchmark_return: float | None = None
    alpha: float | None = None
    if benchmark_series and len(benchmark_series) >= 2:
        b_sorted = sorted(benchmark_series, key=lambda x: x[0])
        b_start = b_sorted[0][1]
        b_end = b_sorted[-1][1]
        if b_start > 0:
            benchmark_return = (b_end - b_start) / b_start
            alpha = total_return - benchmark_return

    return BacktestMetrics(
        cagr=cagr, total_return=total_return, sharpe=sharpe,
        max_drawdown=mdd, win_rate=win_stats["win_rate"],
        avg_win=win_stats["avg_win"], avg_loss=win_stats["avg_loss"],
        monthly_returns=monthly,
        benchmark_return=benchmark_return, alpha=alpha,
        trade_count=len(trades),
    )
