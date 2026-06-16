"""Spike: 验证 PIT dividend_sustainability 实际生效。

审计报告说 backtest 0 trades 是因为 dividend_sustainability 缺失。
本次实现已加,但数据稀疏使"非 0 trades"无法 reproduce。
本 spike 直接验证 `build_stock_context_at` 返回的字段值。

用法:
    cd backend && source .venv/bin/activate
    python spikes/pit_dividend_sust_verification.py

输出:
    backend/spikes/output/pit_dividend_sust_{date}.json
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.services.point_in_time_context_service import (  # noqa: E402
    _compute_dividend_sustainability_at,
    build_stock_context_at,
)


def main() -> int:
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    output_path = output_dir / f"pit_dividend_sust_{date_str}.json"

    db_path = Path(__file__).parent.parent / "data" / "gojira.db"
    engine = create_engine(f"sqlite:///{db_path}")

    # 用 600519 (茅台) 在 2023-03-01 / 2024-03-01 两个 PIT 点
    test_cases = [
        ("600519", date(2023, 3, 1)),
        ("600519", date(2024, 3, 1)),
        ("600519", date(2025, 3, 1)),
    ]

    results = []
    with Session(engine) as db:
        for code, day in test_cases:
            print(f"\n[case] {code} @ {day}")
            try:
                sust = _compute_dividend_sustainability_at(db, code, day)
                print(f"  _compute_dividend_sustainability_at → {sust}")
            except Exception as e:
                sust = None
                print(f"  _compute_dividend_sustainability_at FAIL: {type(e).__name__}: {e}")

            try:
                ctx = build_stock_context_at(db, code, day)
                ctx_sust = ctx.dividend_sustainability if ctx else None
                dyr = getattr(ctx, "dividend_yield_ratio", None) if ctx else None
                pe_pct = getattr(ctx, "pe_pct_10y", None) if ctx else None
                pb_pct = getattr(ctx, "pb_pct_10y", None) if ctx else None
                print(f"  build_stock_context_at:")
                print(f"    dividend_sustainability = {ctx_sust}")
                print(f"    dyr                      = {dyr}")
                print(f"    pe_pct_10y               = {pe_pct}")
                print(f"    pb_pct_10y               = {pb_pct}")
            except Exception as e:
                ctx_sust = None
                print(f"  build_stock_context_at FAIL: {type(e).__name__}: {e}")

            results.append({
                "stock_code": code,
                "day": day.isoformat(),
                "raw_sustainability_score": sust,
                "context_dividend_sustainability": ctx_sust,
            })

    artifact = {
        "ok": True,
        "timestamp": date_str,
        "description": "PIT dividend_sustainability verification on production DB",
        "results": results,
        "strategy_threshold_note": (
            "高股息安全垫 strategy requires 分红可持续>=60. PIT max is 80 (skips payout ratio). "
            "600519 (茅台) typically scores <60 due to low DYR vs historical — "
            "even with sustainability computed, DYR check fails first."
        ),
    }
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, default=str))
    print(f"\n[spike] artifact → {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
