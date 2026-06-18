"""Test backtest_engine — end-to-end run with production strategy_engine."""
from datetime import date, datetime
import pytest

from app.models.backtest_run import BacktestRun
from app.models.broker_fee_config import BrokerFeeConfig
from app.models.historical_kline import HistoricalKline
from app.models.historical_valuation import HistoricalValuation
from app.models.stock import Stock
from app.models.strategy import Strategy
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


@pytest.fixture
def dyr_strategy(db_session):
    """Simple strategy: dyr >= 0.04 — uses a directly-available field."""
    s = Strategy(
        name="Test DYR", slug="test_dyr",
        description="",
        rule_json='{"logic":"AND","conditions":[{"field":"dyr","op":">=","value":0.04}]}',
        is_builtin=False,
    )
    db_session.add(s)
    db_session.flush()
    return s


def test_get_trading_days_returns_dates(db_session, setup):
    """Extract distinct trading days from kline table."""
    days = _get_trading_days(db_session, date(2024, 1, 1), date(2024, 1, 31))
    assert len(days) == 5
    assert days[0] == date(2024, 1, 2)
    assert days[-1] == date(2024, 1, 8)


def test_run_backtest_no_strategies_no_trades(db_session, setup):
    """No strategies in config → no signals → no trades, just track cash."""
    run = BacktestRun(
        config_json={
            "stock_codes": ["600519"],
            "start_date": "2024-01-02",
            "end_date": "2024-01-08",
            "initial_capital": 1000000,
            "slippage_bps": 10,
            "strategies": [],
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
            "strategies": [],
        },
        status="pending",
    )
    db_session.add(run); db_session.flush()
    run_backtest(db_session, run.id)
    db_session.commit()

    refreshed = db_session.get(BacktestRun, run.id)
    curve = refreshed.result_json["equity_curve"]
    assert len(curve) == 5  # 5 trading days
    assert all("date" in p and "value" in p for p in curve)
    assert all(p["value"] == 1000000.0 for p in curve)


def test_run_backtest_with_passing_strategy_buys(db_session, setup, dyr_strategy):
    """When strategy passes on all days, engine should BUY on day 1 and hold."""
    # Set dyr above threshold on all days
    db_session.query(HistoricalValuation).update({"dyr": 0.05})
    db_session.flush()

    run = BacktestRun(
        config_json={
            "stock_codes": ["600519"],
            "start_date": "2024-01-02",
            "end_date": "2024-01-08",
            "initial_capital": 1000000,
            "slippage_bps": 0,
            "strategies": [dyr_strategy.id],
            "target_pct": 0.5,  # use 50% of capital
        },
        status="pending",
    )
    db_session.add(run); db_session.flush()
    run_backtest(db_session, run.id)
    db_session.commit()

    refreshed = db_session.get(BacktestRun, run.id)
    metrics = refreshed.result_json["metrics"]
    assert metrics["trade_count"] >= 1


def test_run_backtest_strategy_fails_no_buy(db_session, setup, dyr_strategy):
    """When strategy never passes (dyr below threshold), no trades."""
    # dyr default None in fixture → strategy fails on all days
    run = BacktestRun(
        config_json={
            "stock_codes": ["600519"],
            "start_date": "2024-01-02",
            "end_date": "2024-01-08",
            "initial_capital": 1000000,
            "slippage_bps": 0,
            "strategies": [dyr_strategy.id],
            "target_pct": 0.5,
        },
        status="pending",
    )
    db_session.add(run); db_session.flush()
    run_backtest(db_session, run.id)
    db_session.commit()

    refreshed = db_session.get(BacktestRun, run.id)
    metrics = refreshed.result_json["metrics"]
    assert metrics["trade_count"] == 0


def test_run_backtest_invalid_run_id_raises(db_session):
    with pytest.raises(HTTPException := __import__("fastapi").HTTPException):
        run_backtest(db_session, 99999)


def test_run_backtest_records_failed_status_on_error(db_session, setup):
    """If engine crashes mid-run, status=failed + error_message set."""
    run = BacktestRun(
        config_json={
            "stock_codes": ["600519"],
            "start_date": "2024-01-02",
            "end_date": "2024-01-08",
            "initial_capital": 1000000,
            "slippage_bps": 0,
            "strategies": [],
            "start_date_INVALID": True,  # will be ignored
        },
        status="pending",
    )
    db_session.add(run); db_session.flush()
    run_backtest(db_session, run.id)
    db_session.commit()
    refreshed = db_session.get(BacktestRun, run.id)
    assert refreshed.status in ("completed", "failed")


def test_backtest_api_submit_list_get(client, db_session):
    """Smoke: POST /api/backtests runs synchronously and returns result."""
    db_session.add(Stock(code="600519", name="贵州茅台", exchange="sh",
                          listing_status="normally_listed"))
    db_session.add(BrokerFeeConfig(
        broker_name="default", commission_rate=0.00025, commission_min=5.0,
        stamp_duty_rate=0.0005, transfer_fee_rate=0.00001,
        effective_from=date(2020, 1, 1), is_active=True,
    ))
    db_session.add(HistoricalKline(
        stock_code="600519", date=date(2024, 1, 2),
        open=100, high=101, low=99, close=100, volume=10000, amount=1000000,
    ))
    db_session.add(HistoricalValuation(
        stock_code="600519", date=date(2024, 1, 2),
        pe_ttm=20, pb=5, sp=100,
    ))
    db_session.flush()

    payload = {
        "stock_codes": ["600519"],
        "start_date": "2024-01-02",
        "end_date": "2024-01-02",
        "initial_capital": 1000000,
        "slippage_bps": 10,
        "strategies": [],
    }
    r = client.post("/api/backtests", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "completed"
    run_id = body["id"]

    r2 = client.get(f"/api/backtests/{run_id}")
    assert r2.status_code == 200
    assert r2.json()["id"] == run_id

    r3 = client.get("/api/backtests")
    assert r3.status_code == 200
    assert any(x["id"] == run_id for x in r3.json())

    r4 = client.get("/api/backtests/99999")
    assert r4.status_code == 404


# ── F21 (2026-06-18): Schema vs Engine alignment ──────────────────────────


def test_backtest_submit_schema_accepts_strategies_field():
    """F21: BacktestSubmit must use 'strategies' (list[int]) not 'strategy_rules'.

    Previously schema had `strategy_rules: list[dict]` but backtest_engine
    reads `config.get("strategies", [])` as list[int] strategy IDs. Schema
    rejected `strategies` field → engine always saw empty list → 0 trades.
    """
    from app.schemas.backtest import BacktestSubmit

    # Should accept strategies field
    payload = BacktestSubmit(
        stock_codes=["600519"],
        start_date="2023-01-03",
        end_date="2023-06-30",
        strategies=[1, 2],
        target_pct=0.20,
    )
    dumped = payload.model_dump()
    assert dumped["strategies"] == [1, 2]
    assert dumped["target_pct"] == 0.20
    # Old field name should NOT be present
    assert "strategy_rules" not in dumped


def test_backtest_submit_schema_default_strategies_empty():
    """F21: default strategies is empty list (matches engine expectation)."""
    from app.schemas.backtest import BacktestSubmit
    payload = BacktestSubmit(
        stock_codes=["600519"],
        start_date="2023-01-03",
        end_date="2023-06-30",
    )
    assert payload.strategies == []
    assert payload.target_pct == 0.10  # default


def test_backtest_api_passes_strategies_to_engine(client, db_session, monkeypatch):
    """F21: POST /api/backtests must pass `strategies` through to config_json.

    Integration test: full HTTP path → DB → run_backtest sees config.
    """
    captured_configs = []
    from app.routers import backtests as backtests_router

    def fake_run_backtest(db, run_id):
        from app.models.backtest_run import BacktestRun
        run = db.get(BacktestRun, run_id)
        captured_configs.append(dict(run.config_json))
        run.status = "completed"
        run.result_json = {"metrics": {}}
        return run

    monkeypatch.setattr(backtests_router, "run_backtest", fake_run_backtest)

    resp = client.post("/api/backtests", json={
        "stock_codes": ["600519"],
        "start_date": "2023-01-03",
        "end_date": "2023-06-30",
        "strategies": [2, 7],
        "target_pct": 0.30,
    })
    assert resp.status_code == 201
    assert len(captured_configs) == 1
    cfg = captured_configs[0]
    assert cfg.get("strategies") == [2, 7], f"Expected [2, 7], got {cfg.get('strategies')}"
    assert cfg.get("target_pct") == 0.30


# ── F26 (2026-06-18): serenity worker watchdog ────────────────────────────


def test_search_one_watchdog_returns_empty_on_hang(monkeypatch):
    """F26: web_search call that hangs past timeout → empty results (not raise)."""
    import time
    from app.services.search_collector_service import _search_one

    class HangingClient:
        class web_search:
            @staticmethod
            def web_search(**kwargs):
                # Simulate GLM SSL read hang — sleep way past timeout
                time.sleep(10)
                return type("R", (), {"search_result": []})()

    rows = _search_one(HangingClient(), "test query", count=5, timeout=1)
    assert rows == [], "Watchdog should return empty list on hang, not raise"


def test_zhipu_client_watchdog_raises_on_llm_hang(monkeypatch):
    """F26: run_serenity_research watchdog raises ZhipuClientError on LLM hang.

    Mock ThreadPoolExecutor.submit to return a future whose .result() raises
    TimeoutError immediately — simulates the watchdog triggering without
    actually waiting for the real timeout (test speed).
    """
    from concurrent.futures import TimeoutError as FutureTimeoutError
    from app.services.llm.zhipu_client import ZhipuClient, ZhipuClientError

    client = ZhipuClient(api_key="fake-key")
    client._model = "fake-model"

    class MockFuture:
        def result(self, timeout=None):
            raise FutureTimeoutError()

    class HangingExecutor:
        def __init__(self, *a, **kw):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def submit(self, fn, *a, **kw):
            return MockFuture()

    monkeypatch.setattr(
        "concurrent.futures.ThreadPoolExecutor", HangingExecutor,
    )

    import pytest
    with pytest.raises(ZhipuClientError) as exc_info:
        client.run_serenity_research(
            user_context="test",
            search_results=[],
        )
    err = str(exc_info.value).lower()
    assert "watchdog" in err or "timeout" in err, \
        f"Expected watchdog/timeout error, got: {exc_info.value}"
