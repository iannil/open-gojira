"""C.1.4 slice runner — create + run + spot-check a slice backtest.

Usage:
    cd backend
    source .venv/bin/activate
    python scripts/run_slice_backtest.py

Slice spec (from Q13):
- strategy: high_dividend_cushion (id=1)
- stock: 600519 茅台
- period: 2023-01-02 → 2023-06-30

Expected: 0 trades (strategy conditions use dyr_fwd / dividend_sustainability
which are None in build_stock_context_at v1). Spot-check should still produce
detailed output per signal, verifying pipeline correctness.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402
from app.models.backtest_run import BacktestRun  # noqa: E402
from app.services.backtest_engine import run_backtest  # noqa: E402


SLICE_STRATEGY_ID = 1  # high_dividend_cushion
SLICE_STOCK = "600519"
SLICE_START = "2023-01-02"
SLICE_END = "2023-06-30"


def main() -> int:
    db = SessionLocal()
    try:
        run = BacktestRun(
            config_json={
                "stock_codes": [SLICE_STOCK],
                "start_date": SLICE_START,
                "end_date": SLICE_END,
                "initial_capital": 1_000_000,
                "slippage_bps": 10,
                "strategies": [SLICE_STRATEGY_ID],
                "target_pct": 0.10,
            },
            status="pending",
        )
        db.add(run); db.flush()
        run_id = run.id
        print(f"Created BacktestRun id={run_id}")

        run_backtest(db, run_id)
        db.commit()

        refreshed = db.get(BacktestRun, run_id)
        print(f"Status: {refreshed.status}")
        if refreshed.status == "failed":
            print(f"Error: {refreshed.error_message}")
            return 1
        metrics = refreshed.result_json["metrics"]
        print(f"Metrics: trade_count={metrics['trade_count']}, "
              f"total_return={metrics['total_return']:.4f}, "
              f"cagr={metrics['cagr']:.4f}, "
              f"sharpe={metrics['sharpe']}, "
              f"max_drawdown={metrics['max_drawdown']:.4f}")
        print(f"Equity curve points: {len(refreshed.result_json['equity_curve'])}")
        print(f"\nNext: run spot-check:")
        print(f"  python scripts/spot_check_backtest.py --run-id {run_id} --sample-per-strategy 5")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
