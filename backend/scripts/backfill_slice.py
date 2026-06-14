"""C.1.2 slice backfill script — fetch 600519 (茅台) × 6 months × 3 endpoints.

Usage:
    cd backend
    source .venv/bin/activate
    python scripts/backfill_slice.py

Verifies historical_data_pipeline works end-to-end before scaling to
309 candidates × 5y. Idempotent — re-running skips existing rows.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure backend/ is on sys.path so `app.*` imports resolve when run from backend/
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402
from app.services.historical_data_pipeline import run_historical_sync  # noqa: E402


SLICE_CODE = "600519"
SLICE_START = "2023-01-01"
SLICE_END = "2023-06-30"


def main() -> int:
    db = SessionLocal()
    try:
        print(f"Backfilling {SLICE_CODE} × {SLICE_START} → {SLICE_END}...")
        summary = run_historical_sync(
            db,
            stock_codes=[SLICE_CODE],
            start_date=SLICE_START,
            end_date=SLICE_END,
        )
        print("Summary:", summary)
        if summary["errors"]:
            print(f"WARNING: {summary['errors']} errors during backfill")
            return 1
        if not (summary["klines"] and summary["valuations"]):
            print("WARNING: 0 klines or valuations inserted — check Lixinger token")
            return 1
        print("OK — slice backfill complete")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
