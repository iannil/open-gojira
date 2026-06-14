"""G1-T1: plan_runner 周期 gate 纯函数测试.

Q8=A 仅买入 gate / Q9=A 单字段 cycle_buy_max 默认 mid / Q10=C 数据缺失 plan-level skip.

Cycle positions (rank 升序 = 越来越高估):
  extreme_low(0) < low(1) < mid(2) < high(3) < extreme_high(4)

Gate logic:
  current_rank > max_rank → block BUY drafts (SELL 仍允许)
"""

import pytest


class TestCyclePositionRank:
    def test_extreme_low_is_rank_0(self):
        from app.services.plan_runner import _cycle_position_rank
        assert _cycle_position_rank("extreme_low") == 0

    def test_low_is_rank_1(self):
        from app.services.plan_runner import _cycle_position_rank
        assert _cycle_position_rank("low") == 1

    def test_mid_is_rank_2(self):
        from app.services.plan_runner import _cycle_position_rank
        assert _cycle_position_rank("mid") == 2

    def test_high_is_rank_3(self):
        from app.services.plan_runner import _cycle_position_rank
        assert _cycle_position_rank("high") == 3

    def test_extreme_high_is_rank_4(self):
        from app.services.plan_runner import _cycle_position_rank
        assert _cycle_position_rank("extreme_high") == 4

    def test_unknown_position_raises(self):
        from app.services.plan_runner import _cycle_position_rank
        with pytest.raises(ValueError):
            _cycle_position_rank("bogus")


class TestCheckCycleGate:
    """_check_cycle_gate(plan_max, current) -> True if BUY drafts should be blocked."""

    def test_block_when_current_above_max(self):
        from app.services.plan_runner import _check_cycle_gate
        # max=mid(2), current=high(3) → 3>2 → block
        assert _check_cycle_gate("mid", "high") is True
        assert _check_cycle_gate("mid", "extreme_high") is True
        # max=low(1), current=mid(2) → 2>1 → block
        assert _check_cycle_gate("low", "mid") is True

    def test_pass_when_current_at_or_below_max(self):
        from app.services.plan_runner import _check_cycle_gate
        # max=mid(2), current=mid(2) → 2>2 false → pass
        assert _check_cycle_gate("mid", "mid") is False
        # max=mid(2), current=low(1) → pass
        assert _check_cycle_gate("mid", "low") is False
        # max=mid(2), current=extreme_low(0) → pass
        assert _check_cycle_gate("mid", "extreme_low") is False

    def test_extreme_high_max_never_blocks(self):
        """Setting cycle_buy_max='extreme_high' effectively disables the gate."""
        from app.services.plan_runner import _check_cycle_gate
        assert _check_cycle_gate("extreme_high", "extreme_high") is False
        assert _check_cycle_gate("extreme_high", "high") is False


class TestRunPlanCycleUnavailable:
    """Q10=C: when cycle_assessment data unavailable, plan run skips entirely."""

    def test_plan_skipped_when_cycle_unavailable(self, db_session, monkeypatch):
        """If assess_cycle returns pe_pct_10y=None, plan run returns early with cycle_unavailable_skipped=True."""
        from app.services.plan_runner import run_plan, PlanRunResult
        from app.services import cycle_assessment_service
        from app.models.plan import Plan

        # Force assess_cycle to return None pe_pct_10y (no Lixinger, no CashflowGoal)
        from app.services.cycle_assessment_service import CycleAssessment
        def _stub_assess_cycle(db):
            return CycleAssessment(
                pe_pct_10y=None,
                pb_pct_10y=None,
                current_pe=None,
                current_pb=None,
                current_dyr=None,
                dyr_index=None,
                cycle_position="mid",  # classify_cycle(None) defaults to "mid"
                position_min=0.4,
                position_max=0.6,
                position_advice="中等估值，正常持有",
            )
        monkeypatch.setattr(
            cycle_assessment_service, "assess_cycle", _stub_assess_cycle
        )

        # Set up minimal plan
        from app.services.data_freshness_service import record_sync_success
        record_sync_success(db_session, "stocks", record_count=1)
        record_sync_success(db_session, "valuation", record_count=1)
        plan = Plan(
            name="t", slug="t-cycle-unavail", status="active",
            strategy_composition_json='{"strategy_ids": [], "logic": "AND"}',
            scan_scope_json='{"kind": "all"}',
            schedule_cron="0 18 * * 1-5",
            is_builtin=False,
            cycle_buy_max="mid",
        )
        db_session.add(plan)
        db_session.flush()

        result = run_plan(db_session, plan)
        assert result.cycle_unavailable_skipped is True
        assert result.cycle_position is None  # set later, after gate check
        assert any("cycle" in e.lower() for e in result.errors)
