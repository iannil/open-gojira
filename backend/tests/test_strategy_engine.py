"""Tests for strategy engine — pure function evaluator."""

import pytest

from app.services.strategy_engine import StockContext, evaluate
from app.schemas.strategy import Condition, StrategyRule


def _make_ctx(**overrides) -> StockContext:
    defaults = dict(
        code="600519",
        name="贵州茅台",
        industry="白酒",
        dyr=0.025,
        pe_pct_10y=0.65,
        pb_pct_10y=0.70,
        dividend_sustainability=80.0,
        ocf_to_ni=1.2,
        qiu_score=3,
        price=1800.0,
        price_52w_high=2000.0,
        price_drop_pct=0.10,
        bank_blind_box=None,
        market_temperature=45.0,
        hq_region="贵州",
        security_theme="消费",
        tier="core",
    )
    defaults.update(overrides)
    return StockContext(**defaults)


class TestEvaluateBasic:
    def test_single_condition_pass(self):
        rule = StrategyRule(logic="AND", conditions=[
            Condition(field="dyr", op=">=", value=0.02),
        ])
        ctx = _make_ctx(dyr=0.04)
        result = evaluate(rule, ctx)
        assert result.passed is True
        assert len(result.condition_results) == 1
        assert result.condition_results[0].passed is True

    def test_single_condition_fail(self):
        rule = StrategyRule(logic="AND", conditions=[
            Condition(field="dyr", op=">=", value=0.05),
        ])
        ctx = _make_ctx(dyr=0.04)
        result = evaluate(rule, ctx)
        assert result.passed is False

    def test_and_logic_all_pass(self):
        rule = StrategyRule(logic="AND", conditions=[
            Condition(field="dyr", op=">=", value=0.04),
            Condition(field="pe_pct_10y", op="<=", value=0.50),
        ])
        ctx = _make_ctx(dyr=0.05, pe_pct_10y=0.30)
        result = evaluate(rule, ctx)
        assert result.passed is True

    def test_and_logic_one_fails(self):
        rule = StrategyRule(logic="AND", conditions=[
            Condition(field="dyr", op=">=", value=0.04),
            Condition(field="pe_pct_10y", op="<=", value=0.50),
        ])
        ctx = _make_ctx(dyr=0.05, pe_pct_10y=0.60)
        result = evaluate(rule, ctx)
        assert result.passed is False

    def test_or_logic_one_passes(self):
        rule = StrategyRule(logic="OR", conditions=[
            Condition(field="dyr", op=">=", value=0.10),
            Condition(field="pe_pct_10y", op="<=", value=0.50),
        ])
        ctx = _make_ctx(dyr=0.04, pe_pct_10y=0.30)
        result = evaluate(rule, ctx)
        assert result.passed is True

    def test_or_logic_all_fail(self):
        rule = StrategyRule(logic="OR", conditions=[
            Condition(field="dyr", op=">=", value=0.10),
            Condition(field="pe_pct_10y", op="<=", value=0.10),
        ])
        ctx = _make_ctx(dyr=0.04, pe_pct_10y=0.60)
        result = evaluate(rule, ctx)
        assert result.passed is False


class TestConditionOps:
    def test_gte(self):
        rule = StrategyRule(logic="AND", conditions=[
            Condition(field="dyr", op=">=", value=0.04),
        ])
        assert evaluate(rule, _make_ctx(dyr=0.04)).passed is True
        assert evaluate(rule, _make_ctx(dyr=0.039)).passed is False

    def test_lte(self):
        rule = StrategyRule(logic="AND", conditions=[
            Condition(field="pe_pct_10y", op="<=", value=0.30),
        ])
        assert evaluate(rule, _make_ctx(pe_pct_10y=0.30)).passed is True
        assert evaluate(rule, _make_ctx(pe_pct_10y=0.31)).passed is False

    def test_eq(self):
        rule = StrategyRule(logic="AND", conditions=[
            Condition(field="bank_blind_box", op="==", value="可见"),
        ])
        assert evaluate(rule, _make_ctx(bank_blind_box="可见")).passed is True
        assert evaluate(rule, _make_ctx(bank_blind_box="模糊")).passed is False

    def test_in_op(self):
        rule = StrategyRule(logic="AND", conditions=[
            Condition(field="industry_in", op="in", value=["银行", "煤炭开采加工"]),
        ])
        assert evaluate(rule, _make_ctx(industry="银行")).passed is True
        assert evaluate(rule, _make_ctx(industry="白酒")).passed is False


class TestDyrFwdField:
    """G3: dyr_fwd field — forward DYR (预期股息率).

    Mirrors `dyr` semantics. None → condition fails (剔除, per Q4 fallback).
    """

    def test_dyr_fwd_gte_pass(self):
        rule = StrategyRule(logic="AND", conditions=[
            Condition(field="dyr_fwd", op=">=", value=0.04),
        ])
        ctx = _make_ctx(forward_dyr=0.05)
        result = evaluate(rule, ctx)
        assert result.passed is True

    def test_dyr_fwd_gte_fail(self):
        rule = StrategyRule(logic="AND", conditions=[
            Condition(field="dyr_fwd", op=">=", value=0.04),
        ])
        ctx = _make_ctx(forward_dyr=0.03)
        result = evaluate(rule, ctx)
        assert result.passed is False

    def test_dyr_fwd_lte_pass(self):
        rule = StrategyRule(logic="AND", conditions=[
            Condition(field="dyr_fwd", op="<=", value=0.05),
        ])
        ctx = _make_ctx(forward_dyr=0.04)
        result = evaluate(rule, ctx)
        assert result.passed is True

    def test_dyr_fwd_none_fails_condition(self):
        """forward_dyr=None → data unavailable → 剔除 (Q4 fallback)."""
        rule = StrategyRule(logic="AND", conditions=[
            Condition(field="dyr_fwd", op=">=", value=0.04),
        ])
        ctx = _make_ctx(forward_dyr=None)
        result = evaluate(rule, ctx)
        assert result.passed is False
        assert result.condition_results[0].passed is False
        assert "data unavailable" in result.condition_results[0].detail

    def test_dyr_fwd_dyr_independent(self):
        """dyr and dyr_fwd resolve independently."""
        rule = StrategyRule(logic="AND", conditions=[
            Condition(field="dyr", op=">=", value=0.06),
            Condition(field="dyr_fwd", op=">=", value=0.04),
        ])
        # Trailing 0.06, Forward 0.04 → both pass
        ctx = _make_ctx(dyr=0.06, forward_dyr=0.04)
        result = evaluate(rule, ctx)
        assert result.passed is True

        # Trailing 0.06, Forward 0.03 → forward fails
        ctx = _make_ctx(dyr=0.06, forward_dyr=0.03)
        result = evaluate(rule, ctx)
        assert result.passed is False


class TestResourceFlagsFields:
    """G4: has_mine + domestic_leader fields for resource_hard_asset strategy.

    invest3 §12 "没矿的有色股他会很警惕" + "国内优先" → both must be True for
    a stock to pass resource_hard_asset. None = data unavailable → 剔除.
    """

    def test_has_mine_field_exists(self):
        ctx = StockContext(code="X")
        assert hasattr(ctx, "has_mine")
        assert ctx.has_mine is None

    def test_domestic_leader_field_exists(self):
        ctx = StockContext(code="X")
        assert hasattr(ctx, "domestic_leader")
        assert ctx.domestic_leader is None

    def test_has_mine_eq_true_passes(self):
        rule = StrategyRule(logic="AND", conditions=[
            Condition(field="has_mine", op="==", value=True),
        ])
        ctx = _make_ctx(has_mine=True)
        result = evaluate(rule, ctx)
        assert result.passed is True

    def test_has_mine_eq_true_fails_when_false(self):
        rule = StrategyRule(logic="AND", conditions=[
            Condition(field="has_mine", op="==", value=True),
        ])
        ctx = _make_ctx(has_mine=False)
        result = evaluate(rule, ctx)
        assert result.passed is False

    def test_has_mine_none_fails(self):
        """has_mine=None → data unavailable → 剔除 (Q4 fallback)."""
        rule = StrategyRule(logic="AND", conditions=[
            Condition(field="has_mine", op="==", value=True),
        ])
        ctx = _make_ctx(has_mine=None)
        result = evaluate(rule, ctx)
        assert result.passed is False
        assert "data unavailable" in result.condition_results[0].detail

    def test_domestic_leader_eq_true_passes(self):
        rule = StrategyRule(logic="AND", conditions=[
            Condition(field="domestic_leader", op="==", value=True),
        ])
        ctx = _make_ctx(domestic_leader=True)
        result = evaluate(rule, ctx)
        assert result.passed is True

    def test_domestic_leader_none_fails(self):
        rule = StrategyRule(logic="AND", conditions=[
            Condition(field="domestic_leader", op="==", value=True),
        ])
        ctx = _make_ctx(domestic_leader=None)
        result = evaluate(rule, ctx)
        assert result.passed is False


class TestNullHandling:
    def test_null_field_fails(self):
        rule = StrategyRule(logic="AND", conditions=[
            Condition(field="dyr", op=">=", value=0.04),
        ])
        ctx = _make_ctx(dyr=None)
        result = evaluate(rule, ctx)
        assert result.passed is False
        assert "unavailable" in result.condition_results[0].detail

    def test_null_in_and_fails(self):
        rule = StrategyRule(logic="AND", conditions=[
            Condition(field="dyr", op=">=", value=0.04),
            Condition(field="pe_pct_10y", op="<=", value=0.50),
        ])
        ctx = _make_ctx(dyr=0.05, pe_pct_10y=None)
        result = evaluate(rule, ctx)
        assert result.passed is False


class TestFields:
    def test_qiu_score(self):
        rule = StrategyRule(logic="AND", conditions=[
            Condition(field="qiu_score", op=">=", value=2),
        ])
        assert evaluate(rule, _make_ctx(qiu_score=3)).passed is True
        assert evaluate(rule, _make_ctx(qiu_score=1)).passed is False

    def test_price_drop_pct(self):
        rule = StrategyRule(logic="AND", conditions=[
            Condition(field="price_drop_pct", op=">=", value=0.20),
        ])
        assert evaluate(rule, _make_ctx(price_drop_pct=0.25)).passed is True
        assert evaluate(rule, _make_ctx(price_drop_pct=0.15)).passed is False

    def test_dividend_sustainability(self):
        rule = StrategyRule(logic="AND", conditions=[
            Condition(field="dividend_sustainability", op=">=", value=60),
        ])
        assert evaluate(rule, _make_ctx(dividend_sustainability=80)).passed is True
        assert evaluate(rule, _make_ctx(dividend_sustainability=50)).passed is False

    def test_ocf_to_ni(self):
        rule = StrategyRule(logic="AND", conditions=[
            Condition(field="ocf_to_ni", op=">=", value=0.80),
        ])
        assert evaluate(rule, _make_ctx(ocf_to_ni=1.2)).passed is True
        assert evaluate(rule, _make_ctx(ocf_to_ni=0.5)).passed is False

    def test_market_temperature(self):
        rule = StrategyRule(logic="AND", conditions=[
            Condition(field="market_temperature", op="<=", value=50),
        ])
        assert evaluate(rule, _make_ctx(market_temperature=45)).passed is True
        assert evaluate(rule, _make_ctx(market_temperature=60)).passed is False


class TestHighDividendCushion:
    """Integration test for the high_dividend_cushion strategy."""

    def test_pass(self):
        rule = StrategyRule.model_validate({
            "logic": "AND",
            "conditions": [
                {"field": "dyr", "op": ">=", "value": 0.04},
                {"field": "dividend_sustainability", "op": ">=", "value": 60},
                {"field": "ocf_to_ni", "op": ">=", "value": 0.80},
            ],
        })
        ctx = _make_ctx(dyr=0.05, dividend_sustainability=80, ocf_to_ni=1.2)
        assert evaluate(rule, ctx).passed is True

    def test_fail_low_dyr(self):
        rule = StrategyRule.model_validate({
            "logic": "AND",
            "conditions": [
                {"field": "dyr", "op": ">=", "value": 0.04},
                {"field": "dividend_sustainability", "op": ">=", "value": 60},
                {"field": "ocf_to_ni", "op": ">=", "value": 0.80},
            ],
        })
        ctx = _make_ctx(dyr=0.03, dividend_sustainability=80, ocf_to_ni=1.2)
        result = evaluate(rule, ctx)
        assert result.passed is False
        assert result.condition_results[0].passed is False
        assert result.condition_results[1].passed is True
        assert result.condition_results[2].passed is True
