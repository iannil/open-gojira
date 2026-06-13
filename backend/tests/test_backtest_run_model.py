"""Test BacktestRun model."""
from datetime import datetime
import pytest

from app.models.backtest_run import BacktestRun


def test_backtest_run_create_pending(db_session):
    r = BacktestRun(
        config_json={
            "strategy_ids": [1, 2],
            "start_date": "2020-01-01",
            "end_date": "2024-12-31",
            "initial_capital": 1000000,
            "slippage_bps": 10,
        },
        status="pending",
    )
    db_session.add(r); db_session.commit()
    assert r.id is not None
    assert r.started_at is None
    assert r.completed_at is None
    assert r.result_json is None


def test_status_values(db_session):
    for status in ("pending", "running", "completed", "failed"):
        db_session.add(BacktestRun(
            config_json={"test": status}, status=status,
        ))
    db_session.commit()
    assert db_session.query(BacktestRun).count() == 4


def test_status_indexed(db_session):
    """status filter is common (find pending/running)."""
    table = BacktestRun.__table__
    assert table.c.status.index


def test_completed_run_has_result(db_session):
    r = BacktestRun(
        config_json={"x": 1}, status="completed",
        result_json={
            "metrics": {"cagr": 0.15, "sharpe": 1.2, "max_drawdown": -0.20},
            "equity_curve": [{"date": "2024-01-01", "value": 1000000}],
            "trades_count": 42,
        },
        started_at=datetime(2026, 6, 12, 10, 0),
        completed_at=datetime(2026, 6, 12, 10, 5),
    )
    db_session.add(r); db_session.commit()
    refreshed = db_session.get(BacktestRun, r.id)
    assert refreshed.result_json["metrics"]["cagr"] == 0.15
    assert refreshed.result_json["trades_count"] == 42


def test_failed_run_has_error(db_session):
    r = BacktestRun(
        config_json={"x": 1}, status="failed",
        error_message="Lixinger circuit open during backtest",
        started_at=datetime(2026, 6, 12, 10, 0),
        completed_at=datetime(2026, 6, 12, 10, 1),
    )
    db_session.add(r); db_session.commit()
    assert r.error_message is not None
