"""C.1.3 spot-check script — sample strategy signals from a backtest run.

Usage:
    cd backend
    source .venv/bin/activate
    # Sample 5 random signals per strategy from run #1:
    python scripts/spot_check_backtest.py --run-id 1 --sample-per-strategy 5
    # Or stratified (2 extreme + 2 boundary + 1 counter-example per strategy):
    python scripts/spot_check_backtest.py --run-id 1 --mode stratified
    # Pin a seed for reproducibility:
    python scripts/spot_check_backtest.py --run-id 1 --seed 42

For each sampled signal, prints:
  - Strategy rule_json + per-condition evaluation
  - Raw data from historical_* tables (point-in-time correct)
  - Sanity status (which fields violate sanity rules, if any)
  - Action taken by engine (BUY / SELL / HOLD)

This is the trust-gate spot-check tool per Q6 decision. Output is for
human visual inspection — terminal stdout.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional

# Ensure backend/ is on sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models.backtest_run import BacktestRun  # noqa: E402
from app.models.historical_financial import HistoricalFinancial  # noqa: E402
from app.models.historical_kline import HistoricalKline  # noqa: E402
from app.models.historical_valuation import HistoricalValuation  # noqa: E402
from app.models.strategy import Strategy  # noqa: E402
from app.schemas.strategy import StrategyRule  # noqa: E402
from app.services.data_sanity_service import validate_record  # noqa: E402
from app.services.point_in_time_context_service import (  # noqa: E402
    build_stock_context_at,
)
from app.services.strategy_engine import evaluate as strategy_evaluate  # noqa: E402


def _fmt_float(v, prec=4) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return str(v)
    try:
        return f"{float(v):.{prec}f}"
    except (ValueError, TypeError):
        return str(v)


def _distance_from_threshold(cond_result) -> Optional[float]:
    """How far actual_value is from threshold (signed). None if incomparable."""
    if cond_result.actual_value is None:
        return None
    try:
        return float(cond_result.actual_value) - float(cond_result.threshold)
    except (ValueError, TypeError):
        return None


def _bucket(signal: dict, threshold_ratio: float = 0.1) -> str:
    """Classify a signal into extreme / boundary / counter buckets.

    `threshold_ratio` is the band around threshold considered "boundary".
    E.g. threshold=0.04, ratio=0.1 → boundary band = [0.036, 0.044].

    Returns one of: 'extreme_pass', 'boundary_pass', 'boundary_fail',
    'extreme_fail', or 'other' (e.g. missing data).
    """
    cond_distances = [
        _distance_from_threshold(cr) for cr in signal["eval"].condition_results
    ]
    numeric_distances = [d for d in cond_distances if d is not None]
    if not numeric_distances:
        return "other"

    passed = signal["eval"].passed
    threshold_vals = [
        float(cr.threshold)
        for cr in signal["eval"].condition_results
        if cr.threshold is not None
    ]
    if not threshold_vals:
        return "other"

    # Use min abs distance ratio (most relevant condition)
    ratios = [
        abs(d) / abs(t) if t else None
        for d, t in zip(numeric_distances, threshold_vals)
    ]
    ratios = [r for r in ratios if r is not None]
    if not ratios:
        return "other"
    min_ratio = min(ratios)

    if passed:
        if min_ratio < threshold_ratio:
            return "boundary_pass"
        return "extreme_pass"
    else:
        if min_ratio < threshold_ratio:
            return "boundary_fail"
        return "extreme_fail"


def _sample_signals(
    db: Session,
    run: BacktestRun,
    strategies: list[Strategy],
    sample_per_strategy: int,
    mode: str,
    seed: Optional[int],
) -> list[dict]:
    """Walk backtest period, evaluate each (day, stock, strategy), sample."""
    cfg = run.config_json or {}
    stock_codes: list[str] = list(cfg.get("stock_codes", []))
    start = datetime.strptime(cfg["start_date"], "%Y-%m-%d").date()
    end = datetime.strptime(cfg["end_date"], "%Y-%m-%d").date()

    trading_days = db.execute(
        select(HistoricalKline.date)
        .where(
            HistoricalKline.date >= start,
            HistoricalKline.date <= end,
            HistoricalKline.stock_code.in_(stock_codes),
        )
        .distinct()
        .order_by(HistoricalKline.date)
    ).scalars().all()

    rng = random.Random(seed)

    all_signals: dict[int, list[dict]] = {s.id: [] for s in strategies}

    for day in trading_days:
        for code in stock_codes:
            kline = db.execute(
                select(HistoricalKline).where(
                    HistoricalKline.stock_code == code,
                    HistoricalKline.date == day,
                )
            ).scalar_one_or_none()
            if not kline:
                continue
            ctx = build_stock_context_at(db, code, day)
            for s in strategies:
                try:
                    rule = StrategyRule.model_validate_json(s.rule_json)
                except Exception:
                    continue
                result = strategy_evaluate(rule, ctx)
                all_signals[s.id].append({
                    "strategy_id": s.id,
                    "strategy_name": s.name,
                    "code": code,
                    "day": day,
                    "ctx": ctx,
                    "rule": rule,
                    "eval": result,
                })

    # Sample per strategy
    sampled: list[dict] = []
    for s in strategies:
        pool = all_signals[s.id]
        if not pool:
            continue
        if mode == "random":
            n = min(sample_per_strategy, len(pool))
            sampled.extend(rng.sample(pool, n))
        elif mode == "stratified":
            buckets: dict[str, list[dict]] = {}
            for sig in pool:
                buckets.setdefault(_bucket(sig), []).append(sig)
            # 2 extreme_pass + 2 boundary_pass + 1 boundary_fail (counter)
            picks: list[dict] = []
            for bucket_name, count in [
                ("extreme_pass", 2),
                ("boundary_pass", 2),
                ("boundary_fail", 1),
            ]:
                b = buckets.get(bucket_name, [])
                picks.extend(rng.sample(b, min(count, len(b))))
            sampled.extend(picks)
    return sampled


def _print_signal(db: Session, sig: dict, idx: int, total: int) -> None:
    s_id = sig["strategy_id"]
    name = sig["strategy_name"]
    code = sig["code"]
    day = sig["day"]
    eval_res = sig["eval"]
    rule = sig["rule"]
    passed = eval_res.passed

    # Load raw data
    kline = db.execute(
        select(HistoricalKline).where(
            HistoricalKline.stock_code == code, HistoricalKline.date == day
        )
    ).scalar_one_or_none()
    valuation = db.execute(
        select(HistoricalValuation).where(
            HistoricalValuation.stock_code == code,
            HistoricalValuation.date == day,
        )
    ).scalar_one_or_none()
    financial = db.execute(
        select(HistoricalFinancial)
        .where(
            HistoricalFinancial.stock_code == code,
            HistoricalFinancial.report_date <= day,
        )
        .order_by(HistoricalFinancial.period.desc())
        .limit(1)
    ).scalar_one_or_none()

    # Sanity check raw valuation record
    sanity_violations: list[str] = []
    if valuation:
        raw = {
            "pe_ttm": valuation.pe_ttm, "pb": valuation.pb,
            "ps_ttm": valuation.ps_ttm, "pcf_ttm": valuation.pcf_ttm,
            "dyr": valuation.dyr, "mc": valuation.mc,
        }
        sanity_violations = validate_record(raw)

    bucket = _bucket(sig)
    day_str = day.isoformat() if hasattr(day, "isoformat") else str(day)
    weekday = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][day.weekday()]

    print()
    print("=" * 78)
    print(f"Signal {idx} of {total} | Strategy: {name} (id={s_id}) | Code: {code}")
    print(f"Date: {day_str} ({weekday}) | Triggered: {'YES' if passed else 'NO'} | Bucket: {bucket}")
    print("-" * 78)
    print("Strategy rule (rule_json):")
    # Pretty-print each condition (from rule) + its evaluation (from result)
    for cond, cr in zip(rule.conditions, eval_res.condition_results):
        check = "✓" if cr.passed else "✗"
        actual = _fmt_float(cr.actual_value)
        threshold = _fmt_float(cr.threshold)
        print(f"  {cond.field} {cond.op} {threshold}  →  CHECK: {cond.field} = {actual}  {check}")
        if cr.detail:
            print(f"      detail: {cr.detail}")
    print()
    print(f"Raw data (point-in-time @ {day_str}):")
    if kline:
        print(f"  kline:   open={_fmt_float(kline.open,2)}  high={_fmt_float(kline.high,2)}  "
              f"low={_fmt_float(kline.low,2)}  close={_fmt_float(kline.close,2)}  "
              f"volume={_fmt_float(kline.volume,0)}")
    else:
        print("  kline:   — (suspended or missing)")
    if valuation:
        print(f"  valu:    pe_ttm={_fmt_float(valuation.pe_ttm,2)}  pb={_fmt_float(valuation.pb,2)}  "
              f"ps_ttm={_fmt_float(valuation.ps_ttm,2)}  pcf_ttm={_fmt_float(valuation.pcf_ttm,2)}")
        print(f"           dyr={_fmt_float(valuation.dyr*100 if valuation.dyr else None,2)}%  "
              f"sp={_fmt_float(valuation.sp,2)}  mc={_fmt_float(valuation.mc/1e8 if valuation.mc else None,2)}亿")
    else:
        print("  valu:    — (missing)")
    if financial:
        print(f"  financ:  period={financial.period}  report_date={financial.report_date}  "
              f"ocf/np={_fmt_float(financial.ocf_to_np_ratio,2)}  roe={_fmt_float(financial.roe,2)}")
    else:
        print("  financ:  — (no report published by this day)")
    print()
    print(f"Sanity status: {'PASS' if not sanity_violations else 'VIOLATION'}")
    for v in sanity_violations:
        print(f"  ! {v}")
    print()
    print(f"Engine action: {'BUY (if not held)' if passed else 'HOLD or SELL (if held)'}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--sample-per-strategy", type=int, default=5)
    parser.add_argument("--mode", choices=["random", "stratified"], default="random")
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        run = db.get(BacktestRun, args.run_id)
        if not run:
            print(f"ERROR: BacktestRun {args.run_id} not found", file=sys.stderr)
            return 1
        cfg = run.config_json or {}
        strategy_ids: list[int] = list(cfg.get("strategies", []))
        if not strategy_ids:
            print("WARNING: no strategies in backtest config — nothing to spot-check")
            return 0
        strategies = list(db.execute(
            select(Strategy).where(Strategy.id.in_(strategy_ids))
        ).scalars().all())

        print(f"Spot-check backtest run #{args.run_id}")
        print(f"  period: {cfg.get('start_date')} → {cfg.get('end_date')}")
        print(f"  universe: {cfg.get('stock_codes')}")
        print(f"  strategies: {[s.name for s in strategies]}")
        print(f"  mode: {args.mode}, sample-per-strategy: {args.sample_per_strategy}, seed: {args.seed}")

        sampled = _sample_signals(
            db, run, strategies,
            sample_per_strategy=args.sample_per_strategy,
            mode=args.mode, seed=args.seed,
        )

        if not sampled:
            print("\nNo signals sampled (universe × period × strategy yielded no evaluations)")
            return 0

        for i, sig in enumerate(sampled, 1):
            _print_signal(db, sig, i, len(sampled))

        print()
        print("=" * 78)
        print(f"Total signals printed: {len(sampled)}")
        print("Review each signal: rule logic correct? raw data sensible? timing reasonable?")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
