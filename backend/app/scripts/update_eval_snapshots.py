#!/usr/bin/env python
"""Generate/update eval set snapshots.

Runs quality_screen rule layer (no LLM) on all 20 eval stocks,
saves rule results as JSON snapshots for baseline comparison.

Usage:
    python -m app.scripts.update_eval_snapshots

This script requires a working database with Lixinger data synced.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

# Add backend dir to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.db.session import SessionLocal
from app.services.eval_stocks import EVAL_STOCKS
from app.services.pipelines.llm.quality_screen_pipeline import screen_stock

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SNAPSHOT_DIR = Path(__file__).resolve().parent.parent.parent / "tests" / "eval" / "companies"


def _rule_result_to_dict(rr) -> dict:
    return {
        "rule_name": rr.rule_name,
        "passed": rr.passed,
        "value": str(rr.value) if rr.value is not None else None,
        "threshold": rr.threshold,
        "note": rr.note,
    }


def update_snapshot(code: str, name: str) -> dict:
    """Run quality_screen (no LLM) and save snapshot."""
    db = SessionLocal()
    try:
        result = screen_stock(db, code, use_llm_for_borderline=False)
        if result is None:
            snap = {"code": code, "name": name, "error": "stock_not_found", "rules": []}
        else:
            snap = {
                "code": code,
                "name": name or result.stock_name,
                "passed": result.passed,
                "borderline": result.borderline,
                "rejected": result.rejected,
                "rules": [_rule_result_to_dict(r) for r in result.rule_results],
                "failed_count": sum(1 for r in result.rule_results if not r.passed),
            }
        path = SNAPSHOT_DIR / f"{code}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False, indent=2)
        logger.info("Updated snapshot: %s (%s)", code, path.name)
        return snap
    finally:
        db.close()


def main():
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for stock in EVAL_STOCKS:
        snap = update_snapshot(stock["code"], stock["name"])
        results.append(snap)

    passed = sum(1 for r in results if r.get("passed"))
    total = len(results)
    print(f"\nSnapshots updated: {total} stocks, {passed} passed, {total - passed} borderlined/rejected")


if __name__ == "__main__":
    main()
