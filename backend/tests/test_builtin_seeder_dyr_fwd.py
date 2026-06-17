"""T4: G3 builtin_seeder — 6 策略 + bank_anchor 预案改用 dyr_fwd.

Per Q3 decision: 6 内置策略凡引用 DYR 的字段统一改为 forward DYR (`dyr_fwd`).
bank_anchor 预案 trading rule 的 dyr_ge/dyr_le triggers 改 dyr_fwd_ge/dyr_fwd_le.
"""

import json

from app.services.builtin_seeder import BUILTIN_PLANS, BUILTIN_STRATEGIES, seed_plans


def _strategy_by_slug(slug: str):
    for s in BUILTIN_STRATEGIES:
        if s["slug"] == slug:
            return s
    raise KeyError(f"strategy {slug} not found")


def _plan_by_slug(slug: str):
    for p in BUILTIN_PLANS:
        if p["slug"] == slug:
            return p
    raise KeyError(f"plan {slug} not found")


class TestBuiltinStrategiesUseDyrFwd:
    """6 内置策略凡引用 DYR 的字段应统一改为 dyr_fwd (forward DYR)."""

    def test_high_dividend_cushion_uses_dyr_fwd(self):
        s = _strategy_by_slug("high_dividend_cushion")
        rule = s["rule"]
        fields = {c["field"] for c in rule["conditions"]}
        assert "dyr_fwd" in fields
        assert "dyr" not in fields

    def test_resource_hard_asset_uses_dyr_fwd(self):
        s = _strategy_by_slug("resource_hard_asset")
        rule = s["rule"]
        fields = {c["field"] for c in rule["conditions"]}
        assert "dyr_fwd" in fields
        assert "dyr" not in fields

    def test_bank_select_uses_dyr_fwd(self):
        s = _strategy_by_slug("bank_select")
        rule = s["rule"]
        fields = {c["field"] for c in rule["conditions"]}
        assert "dyr_fwd" in fields
        assert "dyr" not in fields

    def test_cashflow_asset_uses_dyr_fwd(self):
        s = _strategy_by_slug("cashflow_asset")
        rule = s["rule"]
        fields = {c["field"] for c in rule["conditions"]}
        assert "dyr_fwd" in fields
        assert "dyr" not in fields

    def test_contrarian_oversold_uses_dyr_fwd(self):
        s = _strategy_by_slug("contrarian_oversold")
        rule = s["rule"]
        fields = {c["field"] for c in rule["conditions"]}
        assert "dyr_fwd" in fields
        assert "dyr" not in fields

    def test_no_builtin_strategy_uses_legacy_dyr(self):
        """After G3 migration, no builtin strategy should reference legacy `dyr`."""
        for s in BUILTIN_STRATEGIES:
            rule = s["rule"]
            for cond in rule["conditions"]:
                assert cond["field"] != "dyr", (
                    f"strategy {s['slug']} still uses legacy 'dyr' field; "
                    f"should be 'dyr_fwd' per G3"
                )


class TestBankSelectUsesBlindBoxVerdict:
    """D1 (2026-06-17 invest-alignment audit): bank_select 接入 bank_analyzer 三维。

    invest2 §11 银行盲盒可视化: 股息 + 地域 + 长周期现金流匹配。bank_analyzer
    输出 blind_box_verdict ("可见"|"模糊"|"不可见"),策略层需以此为 hard filter。
    顺便修复 industry_in ["bank"] 永不匹配 Lixinger "银行" 的 bug。
    """

    def test_bank_select_has_blind_box_condition(self):
        s = _strategy_by_slug("bank_select")
        rule = s["rule"]
        bb_conds = [
            c for c in rule["conditions"]
            if c["field"] == "bank_blind_box"
            and c["op"] == "=="
            and c["value"] == "可见"
        ]
        assert len(bb_conds) == 1, (
            "bank_select 必须包含 bank_blind_box=='可见' (invest2 §11)"
        )

    def test_bank_select_industry_includes_chinese(self):
        s = _strategy_by_slug("bank_select")
        rule = s["rule"]
        ind_conds = [c for c in rule["conditions"] if c["field"] == "industry_in"]
        assert len(ind_conds) == 1
        values = ind_conds[0]["value"]
        assert "银行" in values, (
            "industry_in 必须包含 '银行' (Lixinger 实际返回值,非 'bank')"
        )

    def test_bank_anchor_scan_scope_includes_chinese(self):
        p = _plan_by_slug("bank_anchor")
        values = p["scan_scope"]["values"]
        assert "银行" in values, (
            "bank_anchor scan_scope 必须包含 '银行' (Lixinger 实际返回值)"
        )


class TestResourceHardAssetG4Rules:
    """G4: resource_hard_asset must require has_mine + domestic_leader (invest3 §12)."""

    def test_resource_hard_asset_requires_has_mine(self):
        s = _strategy_by_slug("resource_hard_asset")
        rule = s["rule"]
        has_mine_conds = [
            c for c in rule["conditions"]
            if c["field"] == "has_mine" and c["op"] == "==" and c["value"] is True
        ]
        assert len(has_mine_conds) == 1, "resource_hard_asset must require has_mine=True"

    def test_resource_hard_asset_requires_domestic_leader(self):
        s = _strategy_by_slug("resource_hard_asset")
        rule = s["rule"]
        dom_conds = [
            c for c in rule["conditions"]
            if c["field"] == "domestic_leader" and c["op"] == "==" and c["value"] is True
        ]
        assert len(dom_conds) == 1, "resource_hard_asset must require domestic_leader=True"


class TestAvoidOvervaluedTechStrategy:
    """D6-A (2026-06-17 invest-alignment audit): invest2 §13 高估值科技/题材股禁投标记。

    此策略是"标记型" — 命中即 suspect。用户在 /strategies/test 单股检测,
    或未来 plan DSL 支持 NOT 逻辑后用于反向 filter。
    """

    def test_avoid_overvalued_tech_exists(self):
        s = _strategy_by_slug("avoid_overvalued_tech")
        assert s is not None

    def test_avoid_overvalued_tech_uses_or(self):
        s = _strategy_by_slug("avoid_overvalued_tech")
        assert s["rule"]["logic"] == "OR"

    def test_avoid_overvalued_tech_conditions(self):
        """任一红旗即标记: PE 历史高位 或 极低股息率。"""
        s = _strategy_by_slug("avoid_overvalued_tech")
        conds = s["rule"]["conditions"]
        fields = {(c["field"], c["op"]) for c in conds}
        assert ("pe_pct_10y", ">=") in fields
        assert ("dyr_fwd", "<") in fields


class TestMidstreamFilterIsActive:
    """D6-B (2026-06-17 invest-alignment audit): invest2 §13 无优势中游禁投。

    plan_runner._should_filter_as_midstream_non_leader 已实现,验证 4 个内置
    plan 的 disable_midstream_filter 默认 False (即 filter 启用)。
    """

    def test_all_builtin_plans_have_midstream_filter_active(self):
        for p in BUILTIN_PLANS:
            # disable_midstream_filter not set in BUILTIN_PLANS → defaults False at ORM
            assert p.get("disable_midstream_filter", False) is False, (
                f"plan {p['slug']} should not disable midstream filter"
            )


class TestBankAnchorPlanUsesDyrFwdTriggers:
    """bank_anchor 预案 trading rule 的 triggers 改 dyr_fwd_ge/dyr_fwd_le."""

    def test_bank_anchor_buy_ladder_uses_dyr_fwd_ge(self):
        p = _plan_by_slug("bank_anchor")
        rules = p["trading_rules"]
        buy_kinds = [step["trigger"]["kind"] for step in rules["buy_ladder"]]
        # at least one dyr_fwd_ge trigger exists
        assert "dyr_fwd_ge" in buy_kinds
        # no legacy dyr_ge
        assert "dyr_ge" not in buy_kinds

    def test_bank_anchor_sell_ladder_uses_dyr_fwd_le(self):
        p = _plan_by_slug("bank_anchor")
        rules = p["trading_rules"]
        sell_kinds = [step["trigger"]["kind"] for step in rules["sell_ladder"]]
        assert "dyr_fwd_le" in sell_kinds
        assert "dyr_le" not in sell_kinds

    def test_no_builtin_plan_uses_legacy_dyr_triggers(self):
        """After G3 migration, no builtin plan trading rule should use legacy dyr_ge/dyr_le."""
        for p in BUILTIN_PLANS:
            tr = p.get("trading_rules")
            if not tr:
                continue
            for step in tr.get("buy_ladder", []):
                kind = step["trigger"]["kind"]
                assert kind != "dyr_ge", (
                    f"plan {p['slug']} buy_ladder still uses legacy 'dyr_ge'"
                )
            for step in tr.get("sell_ladder", []):
                kind = step["trigger"]["kind"]
                assert kind != "dyr_le", (
                    f"plan {p['slug']} sell_ladder still uses legacy 'dyr_le'"
                )


class TestSeedPlansUpdatesTradingRules:
    """G3 bug fix: seed_plans must update trading_rules_json on existing rows.

    Previously seed_plans only refreshed scan_scope / composition / name / description.
    Stale trading_rules_json (e.g. legacy `dyr_ge`) would persist forever.
    """

    def test_seed_plans_updates_trading_rules_on_existing_row(self, db_session):
        from app.models.plan import Plan

        # Insert an old-shape bank_anchor plan with legacy dyr_ge trigger
        old_rules = {
            "buy_ladder": [{"trigger": {"kind": "dyr_ge", "value": 0.06}, "add_pct": 0.3}],
            "sell_ladder": [{"trigger": {"kind": "dyr_le", "value": 0.03}, "reduce_pct_of_position": 0.5}],
            "invalidation": [],
            "cooldown_days": 5,
        }
        # Pre-seed strategies so plan seeder can resolve strategy_slugs
        from app.services.builtin_seeder import seed_strategies
        seed_strategies(db_session)

        plan = Plan(
            name="legacy bank_anchor",
            slug="bank_anchor",
            description="legacy",
            status="active",
            strategy_composition_json=json.dumps({"strategy_ids": [], "logic": "AND"}),
            scan_scope_json=json.dumps({"kind": "industry_in", "industries": ["bank"]}),
            schedule_cron="0 18 * * 1-5",
            trading_rules_json=json.dumps(old_rules),
            is_builtin=True,
        )
        db_session.add(plan)
        db_session.flush()

        # Re-seed — should overwrite trading_rules_json with new dyr_fwd_* triggers
        seed_plans(db_session)
        db_session.flush()

        refreshed = db_session.get(Plan, plan.id)
        rules = json.loads(refreshed.trading_rules_json)
        buy_kinds = [s["trigger"]["kind"] for s in rules["buy_ladder"]]
        sell_kinds = [s["trigger"]["kind"] for s in rules["sell_ladder"]]
        assert "dyr_fwd_ge" in buy_kinds
        assert "dyr_fwd_le" in sell_kinds
        assert "dyr_ge" not in buy_kinds
        assert "dyr_le" not in sell_kinds
