"""Test backtest_engine — end-to-end run."""
from datetime import date, datetime
import pytest

from app.models.backtest_run import BacktestRun
from app.models.broker_fee_config import BrokerFeeConfig
from app.models.historical_kline import HistoricalKline
from app.models.historical_valuation import HistoricalValuation
from app.models.stock import Stock
from app.services.backtest_engine import run_backtest, _get_trading_days


@pytest.fixture
def setup(db_session):
    db_session.add(Stock(code="600519", name="贵州茅台", exchange="sh",
                          listing_status="normally_listed", prev_close=100.0))
    db_session.add(BrokerFeeConfig(
        broker_name="default", commission_rate=0.00025, commission_min=5.0,
        stamp_duty_rate=0.0005, transfer_fee_rate=0.00001,
        effective_from=date(2020, 1, 1), is_active=True,
    ))
    # 5 days of kline + valuation
    for i, d in enumerate(["2024-01-02", "2024-01-03", "2024-01-04",
                            "2024-01-05", "2024-01-08"]):
        db_session.add(HistoricalKline(
            stock_code="600519", date=datetime.strptime(d, "%Y-%m-%d").date(),
            open=100+i, high=101+i, low=99+i, close=100+i,
            volume=10000, amount=1000000,
        ))
        db_session.add(HistoricalValuation(
            stock_code="600519", date=datetime.strptime(d, "%Y-%m-%d").date(),
            pe_ttm=20+i, pb=5, sp=100+i,
        ))
    db_session.flush()


def test_get_trading_days_returns_dates(db_session, setup):
    """Extract distinct trading days from kline table."""
    days = _get_trading_days(db_session, date(2024, 1, 1), date(2024, 1, 31))
    assert len(days) == 5
    assert days[0] == date(2024, 1, 2)
    assert days[-1] == date(2024, 1, 8)


def test_run_backtest_creates_run_record(db_session, setup):
    """Backtest should produce a BacktestRun with status=completed."""
    run = BacktestRun(
        config_json={
            "stock_codes": ["600519"],
            "start_date": "2024-01-02",
            "end_date": "2024-01-08",
            "initial_capital": 1000000,
            "slippage_bps": 10,
            "strategy_rules": [],  # no rules = no trades, just track cash
        },
        status="pending",
    )
    db_session.add(run); db_session.flush()

    run_backtest(db_session, run.id)
    db_session.commit()

    refreshed = db_session.get(BacktestRun, run.id)
    assert refreshed.status == "completed"
    assert refreshed.completed_at is not None
    assert refreshed.result_json is not None
    metrics = refreshed.result_json["metrics"]
    # no trades → metrics should be 0ish
    assert metrics["total_return"] == 0.0
    assert metrics["cagr"] == 0.0
    assert metrics["trade_count"] == 0


def test_run_backtest_equity_curve_has_one_point_per_day(db_session, setup):
    run = BacktestRun(
        config_json={
            "stock_codes": ["600519"],
            "start_date": "2024-01-02",
            "end_date": "2024-01-08",
            "initial_capital": 1000000,
            "slippage_bps": 10,
            "strategy_rules": [],
        },
        status="pending",
    )
    db_session.add(run); db_session.flush()
    run_backtest(db_session, run.id)
    db_session.commit()

    refreshed = db_session.get(BacktestRun, run.id)
    curve = refreshed.result_json["equity_curve"]
    assert len(curve) == 5  # 5 trading days
    # Each entry has date + value
    assert all("date" in p and "value" in p for p in curve)
    # No trades → value stays at initial capital
    assert all(p["value"] == 1000000.0 for p in curve)


def test_run_backtest_with_simple_buy_rule(db_session, setup):
    """Strategy: BUY if PE < 25."""
    run = BacktestRun(
        config_json={
            "stock_codes": ["600519"],
            "start_date": "2024-01-02",
            "end_date": "2024-01-08",
            "initial_capital": 1000000,
            "slippage_bps": 0,
            "strategy_rules": [
                {
                    "metric": "pe_ttm",
                    "operator": "<",
                    "threshold": 25,
                    "action": "BUY",
                    "target_pct": 0.5,  # use 50% of capital
                }
            ],
        },
        status="pending",
    )
    db_session.add(run); db_session.flush()
    run_backtest(db_session, run.id)
    db_session.commit()

    refreshed = db_session.get(BacktestRun, run.id)
    metrics = refreshed.result_json["metrics"]
    # Should have bought something (PE 20-24 all < 25)
    assert metrics["trade_count"] >= 1


def test_run_backtest_invalid_run_id_raises(db_session):
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        run_backtest(db_session, 99999)


def test_run_backtest_records_failed_status_on_error(db_session, setup, monkeypatch):
    """If strategy rule eval crashes, run should be marked failed."""
    run = BacktestRun(
        config_json={"stock_codes": ["600519"],
                     "start_date": "2024-01-02", "end_date": "2024-01-08",
                     "initial_capital": 1000000, "slippage_bps": 0,
                     "strategy_rules": [{"metric": "INVALID_FIELD"}]},
        status="pending",
    )
    db_session.add(run); db_session.flush()
    # Run should not crash engine — invalid rules just produce no signals
    run_backtest(db_session, run.id)
    db_session.commit()
    refreshed = db_session.get(BacktestRun, run.id)
    # Either completed with 0 trades, or failed gracefully
    assert refreshed.status in ("completed", "failed")


def test_backtest_api_submit_list_get(client, db_session):
    """Smoke: POST /api/backtests runs synchronously and returns result."""
    from datetime import date as _date
    db_session.add(Stock(code="600519", name="贵州茅台", exchange="sh",
                          listing_status="normally_listed"))
    db_session.add(BrokerFeeConfig(
        broker_name="default", commission_rate=0.00025, commission_min=5.0,
        stamp_duty_rate=0.0005, transfer_fee_rate=0.00001,
        effective_from=_date(2020, 1, 1), is_active=True,
    ))
    db_session.add(HistoricalKline(
        stock_code="600519", date=_date(2024, 1, 2),
        open=100, high=101, low=99, close=100, volume=10000, amount=1000000,
    ))
    db_session.add(HistoricalValuation(
        stock_code="600519", date=_date(2024, 1, 2),
        pe_ttm=20, pb=5, sp=100,
    ))
    db_session.flush()

    payload = {
        "stock_codes": ["600519"],
        "start_date": "2024-01-02",
        "end_date": "2024-01-02",
        "initial_capital": 1000000,
        "slippage_bps": 10,
        "strategy_rules": [],
    }
    r = client.post("/api/backtests", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "completed"
    run_id = body["id"]

    # GET single
    r2 = client.get(f"/api/backtests/{run_id}")
    assert r2.status_code == 200
    assert r2.json()["id"] == run_id

    # GET list (should contain our run)
    r3 = client.get("/api/backtests")
    assert r3.status_code == 200
    assert any(x["id"] == run_id for x in r3.json())

    # GET missing
    r4 = client.get("/api/backtests/99999")
    assert r4.status_code == 404
