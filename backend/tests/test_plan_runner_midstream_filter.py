"""G2-T1: plan_runner 中游过滤 (midstream filter).

Per Q5/Q6/Q7 decisions:
- Q5=A: Pattern 级 `is_midstream` (17 patterns, 2 midstream)
- Q6=B: Stock 级 `is_cost_leader` (Seeder 预填 + null = inconclusive)
- Q7=B: plan_runner 扫描后过滤 (Plan.disable_midstream_filter 默认 false)

Filter rule: if pattern.is_midstream=true AND stock.is_cost_leader != true → 剔除.
"""

import pytest
from datetime import date

from app.models.business_pattern import BusinessPattern
from app.models.plan import Plan
from app.models.stock import Stock


@pytest.fixture
def midstream_pattern(db_session):
    bp = BusinessPattern(
        name="煤化工",
        first_principle_variable="煤油价差套利",
        power_tier_baseline=2,
        is_midstream=True,
        is_builtin=True,
    )
    db_session.add(bp)
    db_session.flush()
    return bp


@pytest.fixture
def upstream_pattern(db_session):
    bp = BusinessPattern(
        name="纯煤开采",
        first_principle_variable="煤价 × 储量 × 品位",
        power_tier_baseline=2,
        is_midstream=False,
        is_builtin=True,
    )
    db_session.add(bp)
    db_session.flush()
    return bp


@pytest.fixture
def plan_no_disable(db_session):
    p = Plan(
        name="test", slug="test-plan", status="active",
        strategy_composition_json='{"strategy_ids": [], "logic": "AND"}',
        scan_scope_json='{"kind": "all"}',
        schedule_cron="0 18 * * 1-5",
        is_builtin=False,
        disable_midstream_filter=False,
    )
    db_session.add(p)
    db_session.flush()
    return p


@pytest.fixture
def plan_disable_filter(db_session):
    p = Plan(
        name="test-disabled", slug="test-plan-disabled", status="active",
        strategy_composition_json='{"strategy_ids": [], "logic": "AND"}',
        scan_scope_json='{"kind": "all"}',
        schedule_cron="0 18 * * 1-5",
        is_builtin=False,
        disable_midstream_filter=True,
    )
    db_session.add(p)
    db_session.flush()
    return p


def _add_stock(db_session, code, pattern_id=None, is_cost_leader=None):
    s = Stock(
        code=code, name=f"测试 {code}",
        business_pattern_id=pattern_id,
        is_cost_leader=is_cost_leader,
    )
    db_session.add(s)
    db_session.flush()
    return s


class TestShouldFilterAsMidstreamNonLeader:
    """Pure-function unit tests for the midstream filter predicate."""

    def test_filter_midstream_non_leader(self, db_session, midstream_pattern, plan_no_disable):
        """Midstream pattern + is_cost_leader=None → filter (剔除)."""
        from app.services.plan_runner import _should_filter_as_midstream_non_leader
        stock = _add_stock(db_session, "700001", pattern_id=midstream_pattern.id, is_cost_leader=None)
        result = _should_filter_as_midstream_non_leader(db_session, stock, plan_no_disable)
        assert result is True

    def test_filter_midstream_explicit_false(self, db_session, midstream_pattern, plan_no_disable):
        """Midstream + is_cost_leader=False → filter."""
        from app.services.plan_runner import _should_filter_as_midstream_non_leader
        stock = _add_stock(db_session, "700002", pattern_id=midstream_pattern.id, is_cost_leader=False)
        result = _should_filter_as_midstream_non_leader(db_session, stock, plan_no_disable)
        assert result is True

    def test_keep_midstream_cost_leader(self, db_session, midstream_pattern, plan_no_disable):
        """Midstream + is_cost_leader=True → keep."""
        from app.services.plan_runner import _should_filter_as_midstream_non_leader
        stock = _add_stock(db_session, "700003", pattern_id=midstream_pattern.id, is_cost_leader=True)
        result = _should_filter_as_midstream_non_leader(db_session, stock, plan_no_disable)
        assert result is False

    def test_keep_upstream_regardless_of_cost_leader(self, db_session, upstream_pattern, plan_no_disable):
        """Upstream pattern + is_cost_leader=None → keep (filter only applies to midstream)."""
        from app.services.plan_runner import _should_filter_as_midstream_non_leader
        stock = _add_stock(db_session, "700004", pattern_id=upstream_pattern.id, is_cost_leader=None)
        result = _should_filter_as_midstream_non_leader(db_session, stock, plan_no_disable)
        assert result is False

    def test_keep_when_plan_disables_filter(self, db_session, midstream_pattern, plan_disable_filter):
        """Plan with disable_midstream_filter=True → keep everything."""
        from app.services.plan_runner import _should_filter_as_midstream_non_leader
        stock = _add_stock(db_session, "700005", pattern_id=midstream_pattern.id, is_cost_leader=None)
        result = _should_filter_as_midstream_non_leader(db_session, stock, plan_disable_filter)
        assert result is False

    def test_keep_when_no_pattern_assigned(self, db_session, plan_no_disable):
        """Stock with no business_pattern_id → keep (filter cannot apply)."""
        from app.services.plan_runner import _should_filter_as_midstream_non_leader
        stock = _add_stock(db_session, "700006", pattern_id=None, is_cost_leader=None)
        result = _should_filter_as_midstream_non_leader(db_session, stock, plan_no_disable)
        assert result is False


class TestSeedBusinessPatternsTagsIsMidstream:
    """Seeder should set is_midstream=True for 煤化工 and 电解铝, False for others."""

    def test_seed_marks_midstream_patterns(self, db_session):
        from app.services.builtin_seeder import seed_business_patterns
        # Pre-seed themes (BusinessPattern FK)
        from app.models.theme import Theme
        for name in ["能源安全", "资源安全", "金融安全", "粮食安全"]:
            db_session.add(Theme(name=name, description=f"{name} theme"))
        db_session.flush()

        seed_business_patterns(db_session)
        db_session.flush()

        coal = db_session.query(BusinessPattern).filter_by(name="煤化工").one()
        alum = db_session.query(BusinessPattern).filter_by(name="电解铝").one()
        coal_mine = db_session.query(BusinessPattern).filter_by(name="纯煤开采").one()
        bank = db_session.query(BusinessPattern).filter_by(name="银行").one()

        assert coal.is_midstream is True
        assert alum.is_midstream is True
        assert coal_mine.is_midstream is False
        assert bank.is_midstream is False


class TestSeedCostLeaders:
    """seed_cost_leaders should set is_cost_leader=True for BFNY/NSLY codes."""

    def test_seed_marks_known_cost_leaders(self, db_session):
        from app.services.builtin_seeder import seed_cost_leaders
        db_session.add(Stock(code="600989", name="宝丰能源"))
        db_session.add(Stock(code="600219", name="南山铝业"))
        db_session.add(Stock(code="000001", name="其他股"))
        db_session.flush()

        updated = seed_cost_leaders(db_session)
        db_session.flush()

        assert updated == 2
        bfny = db_session.get(Stock, "600989")
        nsly = db_session.get(Stock, "600219")
        other = db_session.get(Stock, "000001")
        assert bfny.is_cost_leader is True
        assert nsly.is_cost_leader is True
        assert other.is_cost_leader is None  # untouched

    def test_seed_skips_missing_stocks(self, db_session):
        from app.services.builtin_seeder import seed_cost_leaders
        # No stocks in DB → all codes skipped, 0 updated
        updated = seed_cost_leaders(db_session)
        assert updated == 0


class TestSeedResourceLeaders:
    """G4: seed_resource_leaders should set has_mine/domestic_leader for known codes."""

    def test_seed_marks_known_resource_leaders(self, db_session):
        from app.services.builtin_seeder import seed_resource_leaders
        db_session.add(Stock(code="600989", name="宝丰能源"))
        db_session.add(Stock(code="601899", name="紫金矿业"))
        db_session.add(Stock(code="000001", name="非资源股"))
        db_session.flush()

        updated = seed_resource_leaders(db_session)
        db_session.flush()

        # 2 stocks updated (the resource ones); the non-resource stock untouched
        assert updated == 2
        bfny = db_session.get(Stock, "600989")
        zjny = db_session.get(Stock, "601899")
        other = db_session.get(Stock, "000001")
        assert bfny.has_mine is True
        assert bfny.domestic_leader is True
        assert zjny.has_mine is True
        assert zjny.domestic_leader is True
        assert other.has_mine is None
        assert other.domestic_leader is None

    def test_seed_resource_leaders_skips_missing(self, db_session):
        from app.services.builtin_seeder import seed_resource_leaders
        updated = seed_resource_leaders(db_session)
        assert updated == 0  # no stocks in DB


class TestSeedTier:
    """B4-1 N1: seed_tier marks invest3 天阶/玄阶 stocks (复用 core/watch)."""

    def test_seed_marks_core_and_watch(self, db_session):
        from app.services.builtin_seeder import (
            seed_tier,
            BUILTIN_HEAVEN_TIER_CODES,
            BUILTIN_MYSTIC_TIER_CODES,
        )
        # invest3 天阶 → core, 玄阶 → watch
        db_session.add(Stock(code="600989", name="宝丰能源"))   # 天阶 (BFNY) → core
        db_session.add(Stock(code="603233", name="大参林"))     # 天阶 (DSL) → core
        db_session.add(Stock(code="002749", name="国光股份"))   # 玄阶 (GGGF) → watch
        db_session.add(Stock(code="603199", name="九华旅游"))   # 玄阶 (九华) → watch
        db_session.add(Stock(code="000001", name="平安银行"))   # unclassified
        db_session.flush()

        updated = seed_tier(db_session)
        db_session.flush()

        # 4 stocks updated (2 core + 2 watch); unclassified untouched
        assert updated == 4
        assert db_session.get(Stock, "600989").tier == "core"
        assert db_session.get(Stock, "603233").tier == "core"
        assert db_session.get(Stock, "002749").tier == "watch"
        assert db_session.get(Stock, "603199").tier == "watch"
        assert db_session.get(Stock, "000001").tier is None

    def test_seed_tier_is_idempotent(self, db_session):
        from app.services.builtin_seeder import seed_tier
        db_session.add(Stock(code="600989", name="宝丰能源", tier="core"))
        db_session.flush()
        updated = seed_tier(db_session)
        assert updated == 0  # already set

    def test_seed_tier_skips_missing_stocks(self, db_session):
        from app.services.builtin_seeder import seed_tier
        # Empty DB
        updated = seed_tier(db_session)
        assert updated == 0

    def test_heaven_and_mystic_codes_disjoint(self):
        """B4-1 N1 safety: heaven and mystic lists must not overlap."""
        from app.services.builtin_seeder import (
            BUILTIN_HEAVEN_TIER_CODES,
            BUILTIN_MYSTIC_TIER_CODES,
        )
        overlap = set(BUILTIN_HEAVEN_TIER_CODES) & set(BUILTIN_MYSTIC_TIER_CODES)
        assert overlap == set(), f"Overlap detected: {overlap}"

    def test_heaven_codes_count_matches_invest3(self):
        """invest3 §五-八章 explicitly lists 7 天阶 stocks."""
        from app.services.builtin_seeder import BUILTIN_HEAVEN_TIER_CODES
        assert len(BUILTIN_HEAVEN_TIER_CODES) == 7

    def test_mystic_codes_count_matches_invest3(self):
        """invest3 §九-十一章 explicitly lists 3 玄阶 stocks."""
        from app.services.builtin_seeder import BUILTIN_MYSTIC_TIER_CODES
        assert len(BUILTIN_MYSTIC_TIER_CODES) == 3


class TestBuiltinBusinessPatternsThesisVars:
    """B4-3 N3: thesis_variables template extension for 进度条战法 + 商品现价."""

    def test_resource_patterns_have_progress_var(self):
        """Each resource pattern should have a 进度 (progress) thesis var (invest3 §九)."""
        from app.services.builtin_seeder import BUILTIN_BUSINESS_PATTERNS
        resource_patterns = [
            p for p in BUILTIN_BUSINESS_PATTERNS
            if p["theme_name"] in {"能源安全", "资源安全", "金融安全"}
            and p["name"] not in {"银行", "保险", "证券", "黄金零售"}
        ]
        assert len(resource_patterns) >= 7, f"Expected ≥7 resource patterns, got {len(resource_patterns)}"
        for p in resource_patterns:
            names = [v["name"] for v in p["thesis_variables"]]
            has_progress = any("进度" in n for n in names)
            assert has_progress, f"{p['name']}: missing 进度 var, current vars: {names}"

    def test_resource_patterns_have_commodity_price_var(self):
        """Each resource pattern should have a commodity price (现货/期货) var (invest3 §五)."""
        from app.services.builtin_seeder import BUILTIN_BUSINESS_PATTERNS
        resource_patterns = [
            p for p in BUILTIN_BUSINESS_PATTERNS
            if p["theme_name"] in {"能源安全", "资源安全", "金融安全"}
            and p["name"] not in {"银行", "保险", "证券"}
        ]
        for p in resource_patterns:
            names = [v["name"] for v in p["thesis_variables"]]
            # Either "价"/"价格"/"期货"/"现货"/"CFR" indicates commodity price tracking
            has_price = any(
                kw in n for n in names
                for kw in ["价", "期货", "现货", "CFR", "金价"]
            )
            assert has_price, f"{p['name']}: missing commodity price var, current vars: {names}"

    def test_thesis_vars_each_pattern_at_least_3(self):
        """All 19 patterns should have ≥3 thesis vars (baseline)."""
        from app.services.builtin_seeder import BUILTIN_BUSINESS_PATTERNS
        for p in BUILTIN_BUSINESS_PATTERNS:
            assert len(p["thesis_variables"]) >= 3, (
                f"{p['name']}: only {len(p['thesis_variables'])} vars"
            )

    def test_new_vars_are_manual_source(self):
        """All new B4-3 N3 vars should be source='manual' (not Lixinger)."""
        from app.services.builtin_seeder import BUILTIN_BUSINESS_PATTERNS
        for p in BUILTIN_BUSINESS_PATTERNS:
            for v in p["thesis_variables"]:
                if any(kw in v["name"] for kw in ["进度", "期货", "现货", "CFR", "London"]):
                    assert v["source"] == "manual", (
                        f"{p['name']}.{v['name']}: expected manual, got {v['source']}"
                    )


class TestSeedDividendCommitments:
    """B4-4 N4: seed_dividend_commitments should set known commitment_pct."""

    def test_seed_marks_btgf_commitment(self, db_session):
        from app.services.builtin_seeder import seed_dividend_commitments
        db_session.add(Stock(code="002170", name="芭田股份"))
        db_session.add(Stock(code="000001", name="平安银行"))
        db_session.flush()

        updated = seed_dividend_commitments(db_session)
        db_session.flush()

        assert updated == 1
        btgf = db_session.get(Stock, "002170")
        assert btgf.dividend_payout_commitment_pct == 0.60
        assert db_session.get(Stock, "000001").dividend_payout_commitment_pct is None

    def test_seed_commitments_is_idempotent(self, db_session):
        from app.services.builtin_seeder import seed_dividend_commitments
        db_session.add(Stock(code="002170", name="芭田股份", dividend_payout_commitment_pct=0.60))
        db_session.flush()
        updated = seed_dividend_commitments(db_session)
        assert updated == 0


class TestDividendCommitmentStrategy:
    """B4-4 N4: dividend_commitment_leader strategy evaluates correctly."""

    def test_strategy_passes_when_commitment_meets_threshold(self):
        from app.services.strategy_engine import StockContext, evaluate
        from app.schemas.strategy import StrategyRule
        rule = StrategyRule.model_validate({
            "logic": "AND",
            "conditions": [
                {"field": "dividend_payout_commitment_pct", "op": ">=", "value": 0.60},
            ],
        })
        ctx = StockContext(code="002170", name="芭田", dividend_payout_commitment_pct=0.60)
        result = evaluate(rule, ctx)
        assert result.passed is True

    def test_strategy_fails_when_below_threshold(self):
        from app.services.strategy_engine import StockContext, evaluate
        from app.schemas.strategy import StrategyRule
        rule = StrategyRule.model_validate({
            "logic": "AND",
            "conditions": [
                {"field": "dividend_payout_commitment_pct", "op": ">=", "value": 0.60},
            ],
        })
        ctx = StockContext(code="000001", name="某股", dividend_payout_commitment_pct=0.40)
        result = evaluate(rule, ctx)
        assert result.passed is False

    def test_strategy_fails_when_commitment_unset(self):
        """None commitment = data unavailable → fail (not pass)."""
        from app.services.strategy_engine import StockContext, evaluate
        from app.schemas.strategy import StrategyRule
        rule = StrategyRule.model_validate({
            "logic": "AND",
            "conditions": [
                {"field": "dividend_payout_commitment_pct", "op": ">=", "value": 0.60},
            ],
        })
        ctx = StockContext(code="000001", name="无承诺股")  # commitment_pct = None
        result = evaluate(rule, ctx)
        assert result.passed is False
