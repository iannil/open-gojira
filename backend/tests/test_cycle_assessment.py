"""Tests for cycle_assessment_service — 逆向仓位法核心逻辑."""

import pytest

from app.services.cycle_assessment_service import (
    CycleAssessment,
    classify_cycle,
    compute_index_percentile,
    POSITION_ADVICE,
)


class TestClassifyCycle:
    def test_extreme_low(self):
        assert classify_cycle(5) == "extreme_low"
        assert classify_cycle(0) == "extreme_low"
        assert classify_cycle(9.9) == "extreme_low"

    def test_low(self):
        assert classify_cycle(10) == "low"
        assert classify_cycle(20) == "low"
        assert classify_cycle(29.9) == "low"

    def test_mid(self):
        assert classify_cycle(30) == "mid"
        assert classify_cycle(50) == "mid"
        assert classify_cycle(69.9) == "mid"

    def test_high(self):
        assert classify_cycle(70) == "high"
        assert classify_cycle(80) == "high"
        assert classify_cycle(89.9) == "high"

    def test_extreme_high(self):
        assert classify_cycle(90) == "extreme_high"
        assert classify_cycle(100) == "extreme_high"

    def test_none_falls_back_to_mid(self):
        assert classify_cycle(None) == "mid"


class TestPositionAdvice:
    def test_every_position_has_valid_range(self):
        for pos, (lo, hi, text) in POSITION_ADVICE.items():
            assert 0 <= lo <= 1, f"{pos} min out of range"
            assert 0 <= hi <= 1, f"{pos} max out of range"
            assert lo <= hi, f"{pos} min > max"
            assert text, f"{pos} missing advice text"

    def test_position_ranges_decrease_monotonically(self):
        positions = ["extreme_low", "low", "mid", "high", "extreme_high"]
        prev_min = 2.0
        for pos in positions:
            lo, hi, _ = POSITION_ADVICE[pos]
            assert lo < prev_min, f"{pos} min ({lo}) not decreasing from previous"
            prev_min = lo


class TestComputeIndexPercentile:
    def test_empty_history(self):
        result = compute_index_percentile([])
        assert result["pe_pct_10y"] is None
        assert result["pb_pct_10y"] is None
        assert result["current_pe"] is None

    def test_single_entry(self):
        history = [{"date": "2025-01-01", "pe_ttm.mcw": 12.0, "pb.mcw": 1.5, "dyr.mcw": 0.03}]
        result = compute_index_percentile(history)
        assert result["pe_pct_10y"] == 100.0
        assert result["pb_pct_10y"] == 100.0
        assert result["current_pe"] == 12.0
        assert result["current_dyr"] == 0.03

    def test_percentile_calculation(self):
        history = [
            {"date": f"2024-{i+1:02d}-01", "pe_ttm.mcw": float(i), "pb.mcw": float(i)}
            for i in range(10)
        ]
        result = compute_index_percentile(history)
        # Latest PE = 9.0, all values <= 9.0 -> 100%
        assert result["pe_pct_10y"] == 100.0
        assert result["current_pe"] == 9.0

    def test_none_values_skipped(self):
        history = [
            {"date": "2024-01-01", "pe_ttm.mcw": None, "pb.mcw": None},
            {"date": "2024-02-01", "pe_ttm.mcw": 12.0, "pb.mcw": 1.5, "dyr.mcw": 0.03},
        ]
        result = compute_index_percentile(history)
        assert result["pe_pct_10y"] == 100.0
        assert result["current_pe"] == 12.0


class TestCycleAssessmentToDict:
    def test_to_dict(self):
        a = CycleAssessment(
            pe_pct_10y=25.0,
            pb_pct_10y=20.0,
            dyr_index=0.035,
            cycle_position="low",
            position_min=0.6,
            position_max=0.8,
            position_advice="低估区间，可积极配置",
        )
        d = a.to_dict()
        assert d["cycle_position"] == "low"
        assert d["position_range"] == [0.6, 0.8]
        assert d["pe_pct_10y"] == 25.0
