"""Tests for plan_runner — dual-pass screening AND/OR logic."""

import pytest
from app.services.strategy_engine import StockContext
from app.schemas.strategy import Condition, StrategyRule


def _make_ctx(**overrides) -> StockContext:
    defaults = dict(
        code="000001", name="测试", industry="银行",
        dyr=0.05, pe_pct_10y=0.30,
        dividend_sustainability=None, ocf_to_ni=None,
    )
    defaults.update(overrides)
    return StockContext(**defaults)


class TestStrategyDefinitelyFails:
    def test_and_one_fails_should_eliminate(self):
        from app.services.plan_runner import _strategy_definitely_fails
        rule = StrategyRule(logic="AND", conditions=[
            Condition(field="dyr", op=">=", value=0.04),
            Condition(field="pe_pct_10y", op="<=", value=0.50),
        ])
        ctx = _make_ctx(dyr=0.03, pe_pct_10y=0.30)
        assert _strategy_definitely_fails(rule, ctx) is True

    def test_and_all_pass_should_keep(self):
        from app.services.plan_runner import _strategy_definitely_fails
        rule = StrategyRule(logic="AND", conditions=[
            Condition(field="dyr", op=">=", value=0.04),
            Condition(field="pe_pct_10y", op="<=", value=0.50),
        ])
        ctx = _make_ctx(dyr=0.05, pe_pct_10y=0.30)
        assert _strategy_definitely_fails(rule, ctx) is False

    def test_or_one_fails_one_passes_should_keep(self):
        from app.services.plan_runner import _strategy_definitely_fails
        rule = StrategyRule(logic="OR", conditions=[
            Condition(field="dyr", op=">=", value=0.10),
            Condition(field="pe_pct_10y", op="<=", value=0.50),
        ])
        ctx = _make_ctx(dyr=0.04, pe_pct_10y=0.30)
        assert _strategy_definitely_fails(rule, ctx) is False

    def test_or_all_fail_should_eliminate(self):
        from app.services.plan_runner import _strategy_definitely_fails
        rule = StrategyRule(logic="OR", conditions=[
            Condition(field="dyr", op=">=", value=0.10),
            Condition(field="pe_pct_10y", op="<=", value=0.10),
        ])
        ctx = _make_ctx(dyr=0.04, pe_pct_10y=0.60)
        assert _strategy_definitely_fails(rule, ctx) is True

    def test_or_one_unavailable_one_passes_should_keep(self):
        from app.services.plan_runner import _strategy_definitely_fails
        rule = StrategyRule(logic="OR", conditions=[
            Condition(field="dividend_sustainability", op=">=", value=60),
            Condition(field="dyr", op=">=", value=0.04),
        ])
        ctx = _make_ctx(dividend_sustainability=None, dyr=0.05)
        assert _strategy_definitely_fails(rule, ctx) is False

    def test_or_all_unavailable_should_keep(self):
        from app.services.plan_runner import _strategy_definitely_fails
        rule = StrategyRule(logic="OR", conditions=[
            Condition(field="dividend_sustainability", op=">=", value=60),
            Condition(field="ocf_to_ni", op=">=", value=0.80),
        ])
        ctx = _make_ctx(dividend_sustainability=None, ocf_to_ni=None)
        assert _strategy_definitely_fails(rule, ctx) is False
