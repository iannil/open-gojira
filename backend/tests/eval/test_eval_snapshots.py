"""Eval Set tests — stock list integrity + snapshot structure validation.

The full quality_screen eval requires a seeded production database.
Run with:
    python -m app.scripts.update_eval_snapshots   # creates/updates snapshots
    pytest tests/eval/test_eval_snapshots.py -v    # validates against snapshots
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.eval_stocks import EVAL_STOCKS

SNAPSHOT_DIR = Path(__file__).resolve().parent / "companies"


def _load_snapshot(code: str) -> dict | None:
    path = SNAPSHOT_DIR / f"{code}.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class TestEvalStockList:
    """Validate EVAL_STOCKS integrity."""

    def test_20_stocks(self):
        assert len(EVAL_STOCKS) == 20

    def test_unique_codes(self):
        codes = [s["code"] for s in EVAL_STOCKS]
        assert len(codes) == len(set(codes)), "Duplicate stock codes"

    def test_all_have_names_and_reasons(self):
        for s in EVAL_STOCKS:
            assert s.get("name"), f"{s['code']} missing name"
            assert s.get("reason"), f"{s['code']} missing reason"

    def test_codes_are_strings(self):
        for s in EVAL_STOCKS:
            assert isinstance(s["code"], str), f"{s['code']} not a string"
            assert len(s["code"]) == 6, f"{s['code']} not 6 chars"


class TestSnapshotFiles:
    """Validate snapshot JSON structure (if snapshots exist)."""

    def test_snapshots_exist(self):
        """Check that at least some snapshot files exist."""
        snap_count = len(list(SNAPSHOT_DIR.glob("*.json")))
        if snap_count == 0:
            pytest.skip("No snapshots found — run: python -m app.scripts.update_eval_snapshots")

    @pytest.mark.parametrize("stock", EVAL_STOCKS, ids=lambda s: s["code"])
    def test_snapshot_has_required_fields(self, stock):
        snap = _load_snapshot(stock["code"])
        if snap is None:
            pytest.skip(f"No snapshot for {stock['code']}")
        assert "code" in snap
        assert "name" in snap
        assert snap["code"] == stock["code"]

    @pytest.mark.parametrize("stock", EVAL_STOCKS, ids=lambda s: s["code"])
    def test_snapshot_has_rules(self, stock):
        snap = _load_snapshot(stock["code"])
        if snap is None:
            pytest.skip(f"No snapshot for {stock['code']}")
        if snap.get("error"):
            pytest.skip(f"{stock['code']}: {snap['error']}")
        assert "rules" in snap
        assert len(snap["rules"]) > 0, f"{stock['code']}: no rules in snapshot"
        for rule in snap["rules"]:
            assert "rule_name" in rule
            assert "passed" in rule
