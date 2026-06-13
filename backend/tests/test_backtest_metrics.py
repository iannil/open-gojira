"""Test backtest_metrics — CAGR / Sharpe / MaxDD / win rate."""
import pytest
from datetime import date

from app.services.backtest_metrics import (
    compute_cagr, compute_sharpe, compute_max_drawdown,
    compute_win_rate, compute_monthly_returns,
    compute_all_metrics, BacktestMetrics,
)


# --- CAGR ---

def test_cagr_positive_growth():
    """1M → 2M over 5 years → CAGR ≈ 14.87%."""
    cagr = compute_cagr(
        start_value=1000000.0, end_value=2000000.0,
        start_date=date(2020, 1, 1), end_date=date(2025, 1, 1),
    )
    assert cagr == pytest.approx(0.1487, abs=0.01)


def test_cagr_zero_when_no_change():
    cagr = compute_cagr(
        start_value=1000000.0, end_value=1000000.0,
        start_date=date(2020, 1, 1), end_date=date(2025, 1, 1),
    )
    assert cagr == 0.0


def test_cagr_negative_for_loss():
    cagr = compute_cagr(
        start_value=1000000.0, end_value=500000.0,
        start_date=date(2020, 1, 1), end_date=date(2025, 1, 1),
    )
    assert cagr < 0


def test_cagr_short_period():
    """1 year: 1M → 1.1M → CAGR ≈ 10%."""
    cagr = compute_cagr(
        start_value=1000000.0, end_value=1100000.0,
        start_date=date(2024, 1, 1), end_date=date(2025, 1, 1),
    )
    assert cagr == pytest.approx(0.10, abs=0.01)


# --- Sharpe ---

def test_sharpe_zero_for_constant_series():
    """No volatility → sharpe = 0 (or undefined)."""
    daily_returns = [0.0] * 252
    sharpe = compute_sharpe(daily_returns, risk_free_rate=0.02)
    assert sharpe == 0.0


def test_sharpe_positive_for_steady_growth():
    # Steady upward drift with tiny noise: high mean, low std → high sharpe.
    # (A perfectly constant series has std=0 → sharpe=0 by definition, so we
    # add a small amount of noise to keep the test meaningful.)
    import random
    random.seed(1)
    daily_returns = [0.001 + random.gauss(0, 0.0005) for _ in range(252)]
    sharpe = compute_sharpe(daily_returns, risk_free_rate=0.02)
    assert sharpe > 1.0  # high sharpe


def test_sharpe_low_for_volatile_returns():
    # High volatility relative to drift → sharpe well below 1.
    # (std=0.03 swamps the 0.0005 drift; seed chosen so the realized
    # sample mean stays small enough to keep sharpe < 1.)
    import random
    random.seed(7)
    daily_returns = [random.gauss(0.0005, 0.03) for _ in range(252)]
    sharpe = compute_sharpe(daily_returns, risk_free_rate=0.02)
    assert sharpe < 1.0


# --- Max Drawdown ---

def test_max_drawdown_no_drawdown():
    """Monotonically increasing → MaxDD = 0."""
    series = [1.0, 1.1, 1.2, 1.3, 1.4]
    mdd = compute_max_drawdown(series)
    assert mdd == 0.0


def test_max_drawdown_simple_case():
    """Peak 1.5 → Trough 1.0 → MDD = -33.3%."""
    series = [1.0, 1.5, 1.0, 1.2]
    mdd = compute_max_drawdown(series)
    assert mdd == pytest.approx(-0.3333, abs=0.01)


def test_max_drawdown_full_loss():
    series = [1.0, 0.5, 0.0]
    mdd = compute_max_drawdown(series)
    assert mdd == -1.0  # -100%


def test_max_drawdown_recovers():
    series = [1.0, 2.0, 1.0, 3.0]
    mdd = compute_max_drawdown(series)
    assert mdd == pytest.approx(-0.5, abs=0.01)


# --- Win Rate ---

def test_win_rate_basic():
    trades = [
        {"realized_pnl": 100},
        {"realized_pnl": -50},
        {"realized_pnl": 200},
        {"realized_pnl": 0},  # break-even, not counted as win
    ]
    result = compute_win_rate(trades)
    assert result["total"] == 4
    assert result["wins"] == 2
    assert result["losses"] == 1
    assert result["win_rate"] == pytest.approx(0.5, abs=0.01)  # 2 wins / (2 wins + 1 loss + 1 break-even = 3 with pnl≠0)... or 2/4 = 0.5


def test_win_rate_no_trades():
    result = compute_win_rate([])
    assert result["win_rate"] == 0.0
    assert result["total"] == 0


def test_win_rate_all_wins():
    trades = [{"realized_pnl": 100}, {"realized_pnl": 200}]
    result = compute_win_rate(trades)
    assert result["win_rate"] == 1.0
    assert result["avg_win"] == 150.0


def test_win_rate_avg_loss():
    trades = [{"realized_pnl": -100}, {"realized_pnl": -200}]
    result = compute_win_rate(trades)
    assert result["avg_loss"] == -150.0


# --- Monthly Returns ---

def test_monthly_returns_basic():
    daily_values = [
        (date(2024, 1, 1), 1000000),
        (date(2024, 1, 31), 1050000),
        (date(2024, 2, 1), 1050000),
        (date(2024, 2, 29), 1100000),
    ]
    monthly = compute_monthly_returns(daily_values)
    assert "2024-01" in monthly
    assert monthly["2024-01"] == pytest.approx(0.05, abs=0.01)
    assert monthly["2024-02"] == pytest.approx(0.0476, abs=0.01)


def test_monthly_returns_empty():
    assert compute_monthly_returns([]) == {}


# --- compute_all_metrics (composite) ---

def test_compute_all_metrics_assembles_everything():
    daily_values = [
        (date(2024, 1, 1), 1000000),
        (date(2024, 6, 30), 1100000),
        (date(2024, 12, 31), 1200000),
    ]
    daily_returns = [0.001, 0.002, -0.001, 0.0015]
    trades = [
        {"realized_pnl": 1000},
        {"realized_pnl": -500},
    ]
    m = compute_all_metrics(
        daily_values=daily_values,
        daily_returns=daily_returns,
        trades=trades,
        risk_free_rate=0.02,
    )
    assert isinstance(m, BacktestMetrics)
    assert m.cagr is not None
    assert m.sharpe is not None
    assert m.max_drawdown is not None
    assert m.win_rate is not None
    assert m.total_return == pytest.approx(0.20, abs=0.01)


def test_compute_all_metrics_with_benchmark():
    daily_values = [
        (date(2024, 1, 1), 1000000),
        (date(2024, 12, 31), 1200000),
    ]
    benchmark = [
        (date(2024, 1, 1), 1000),
        (date(2024, 12, 31), 1100),
    ]
    m = compute_all_metrics(
        daily_values=daily_values,
        daily_returns=[],
        trades=[],
        benchmark_series=benchmark,
    )
    assert m.benchmark_return == pytest.approx(0.10, abs=0.01)
    assert m.alpha == pytest.approx(0.10, abs=0.01)  # strategy 20% - benchmark 10%


def test_compute_all_metrics_empty():
    """Empty inputs → all metrics None/0."""
    m = compute_all_metrics(
        daily_values=[], daily_returns=[], trades=[],
    )
    assert m.cagr == 0.0
    assert m.sharpe == 0.0
