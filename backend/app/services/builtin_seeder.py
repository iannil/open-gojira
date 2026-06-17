"""Builtin seeder — initializes built-in strategies and plans at startup.

Idempotent: checks by slug before inserting.
"""

from __future__ import annotations

import json
import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.broker_fee_config import BrokerFeeConfig
from app.models.business_pattern import BusinessPattern
from app.models.plan import Plan
from app.models.stock import Stock
from app.models.strategy import Strategy
from app.models.theme import Theme
from app.services.trading_calendar_service import seed_all_years

logger = logging.getLogger(__name__)

# ── Builtin strategies ───────────────────────────────────────────────

BUILTIN_STRATEGIES = [
    {
        "slug": "high_dividend_cushion",
        "name": "高股息安全垫",
        "description": "股息率≥4%、分红可持续性≥60、经营现金流/净利润≥0.8",
        "rule": {
            "logic": "AND",
            "conditions": [
                {"field": "dyr_fwd", "op": ">=", "value": 0.04},
                {"field": "dividend_sustainability", "op": ">=", "value": 60},
                {"field": "ocf_to_ni", "op": ">=", "value": 0.80},
            ],
        },
    },
    {
        "slug": "undervalued_entry",
        "name": "低估值买入信号",
        "description": "PE 10年分位≤30%、PB 10年分位≤30%",
        "rule": {
            "logic": "AND",
            "conditions": [
                {"field": "pe_pct_10y", "op": "<=", "value": 0.30},
                {"field": "pb_pct_10y", "op": "<=", "value": 0.30},
            ],
        },
    },
    {
        "slug": "resource_hard_asset",
        "name": "资源类硬资产",
        "description": "预期股息率≥4%、PB分位≤50%、有矿+国内领先+扩产可见+地缘稳定(invest3 §12 完整 7 维)",
        "rule": {
            "logic": "AND",
            "conditions": [
                {"field": "dyr_fwd", "op": ">=", "value": 0.04},
                {"field": "pb_pct_10y", "op": "<=", "value": 0.50},
                {"field": "has_mine", "op": "==", "value": True},
                {"field": "domestic_leader", "op": "==", "value": True},
                {"field": "expansion_outlook", "op": "==", "value": True},
                {"field": "geo_risk", "op": "==", "value": True},
            ],
        },
    },
    {
        "slug": "bank_select",
        "name": "银行业精选",
        "description": "银行行业、股息率≥5%、盲盒可视化=可见 (invest2 §11 三维: 股息+地域+现金流)",
        "rule": {
            "logic": "AND",
            "conditions": [
                # D1 修复: Lixinger 实际返回 industry="银行" (中文),
                # 旧值 ["bank"] 永不匹配。补 "bank" 兼容未来数据源变更。
                {"field": "industry_in", "op": "in", "value": ["银行", "bank"]},
                {"field": "dyr_fwd", "op": ">=", "value": 0.05},
                # D1 新增: 接入 bank_analyzer_service 的 blind_box_verdict,
                # 严格对齐 invest2 §11 "挑能看见东西的"。
                {"field": "bank_blind_box", "op": "==", "value": "可见"},
            ],
        },
    },
    {
        "slug": "cashflow_asset",
        "name": "现金流资产",
        "description": "经营现金流/净利润≥1.0、股息率≥4%、PE分位≤50%",
        "rule": {
            "logic": "AND",
            "conditions": [
                {"field": "ocf_to_ni", "op": ">=", "value": 1.0},
                {"field": "dyr_fwd", "op": ">=", "value": 0.04},
                {"field": "pe_pct_10y", "op": "<=", "value": 0.50},
            ],
        },
    },
    {
        "slug": "contrarian_oversold",
        "name": "超跌逆向机会",
        "description": "距52周高点跌幅≥20%、股息率≥4%、分红可持续性≥50",
        "rule": {
            "logic": "AND",
            "conditions": [
                {"field": "price_drop_pct", "op": ">=", "value": 0.20},
                {"field": "dyr_fwd", "op": ">=", "value": 0.04},
                {"field": "dividend_sustainability", "op": ">=", "value": 50},
            ],
        },
    },
    {
        # D6-A (2026-06-17 invest-alignment audit): invest2 §13 三类禁投之一。
        # 此为"标记型"策略 — 命中即 suspect, 用户在 UI 上看到应警惕。
        # 不直接进 plan composition (plan DSL 是正向逻辑), 用作 /strategies/test 单股检测。
        "slug": "avoid_overvalued_tech",
        "name": "回避高估值题材",
        "description": "PE 10年分位≥90% 或 预期股息率<2% (invest2 §13 高估值科技/题材股红旗)",
        "rule": {
            "logic": "OR",
            "conditions": [
                {"field": "pe_pct_10y", "op": ">=", "value": 0.90},
                {"field": "dyr_fwd", "op": "<", "value": 0.02},
            ],
        },
    },
]

# ── Builtin business patterns ─────────────────────────────────────────
# Source: invest1/2/3 methodology. See docs/progress for design rationale.
# theme_name is resolved to theme_id at seed time (themes seeded earlier).
# lixinger_industries: industry strings Lixinger returns in Stock.industry.
#   1:1 → auto-infer Stock.business_pattern_id
#   1:0 / 1:多 → leave null, force manual tag

BUILTIN_BUSINESS_PATTERNS: list[dict] = [
    # ── 资源安全 (id=2) ─────────────────────────────────────────────
    {
        "name": "煤化工",
        "theme_name": "能源安全",
        "description": "煤制烯烃/煤制油,核心是煤油价差套利",
        "first_principle_variable": "煤油价差套利",
        "power_tier_baseline": 2,
        "is_midstream": True,
        "thesis_variables": [
            {"name": "煤油比", "unit": "", "source": "manual"},
            {"name": "烯烃吨成本", "unit": "元/吨", "source": "manual"},
            {"name": "产能利用率", "unit": "%", "source": "manual"},
        ],
        "lixinger_industries": ["化学原料", "化学制品", "煤化工"],
        "source_ref": "invest1 第二章; invest2 BFNY; invest3 §12",
    },
    {
        "name": "纯煤开采",
        "theme_name": "能源安全",
        "description": "煤炭开采(非化工),核心是煤价 × 储量 × 品位",
        "first_principle_variable": "煤价 × 可采储量 × 品位",
        "power_tier_baseline": 2,
        "thesis_variables": [
            {"name": "吨煤售价", "unit": "元/吨", "source": "manual"},
            {"name": "单位生产成本", "unit": "元/吨", "source": "manual"},
            {"name": "可采储量", "unit": "亿吨", "source": "manual"},
        ],
        "lixinger_industries": ["煤炭开采", "煤炭"],
        "source_ref": "invest3 §12",
    },
    {
        "name": "电解铝",
        "theme_name": "资源安全",
        "description": "电解铝生产,核心是电力成本套利(出海印尼)",
        "first_principle_variable": "电力成本套利(出海)",
        "power_tier_baseline": 1,
        "is_midstream": True,
        "thesis_variables": [
            {"name": "电价成本", "unit": "元/度", "source": "manual"},
            {"name": "氧化铝价格", "unit": "元/吨", "source": "manual"},
            {"name": "电解铝产能", "unit": "万吨", "source": "manual"},
        ],
        # 注意:"铝"行业同时包含电解铝和铝上游,1:多歧义 → 留 null 手标
        "lixinger_industries": ["工业金属", "有色冶炼"],
        "source_ref": "invest1 第二章; invest2 NSLY",
    },
    {
        "name": "铝上游",
        "theme_name": "资源安全",
        "description": "铝土矿/氧化铝,核心是矿端成本",
        "first_principle_variable": "铝土矿自给率与氧化铝价差",
        "power_tier_baseline": 2,
        "thesis_variables": [
            {"name": "铝土矿自给率", "unit": "%", "source": "manual"},
            {"name": "氧化铝售价", "unit": "元/吨", "source": "manual"},
            {"name": "海外项目产能", "unit": "万吨", "source": "manual"},
        ],
        "lixinger_industries": ["工业金属", "有色冶炼"],
        "source_ref": "invest3 §12",
    },
    {
        "name": "磷化工",
        "theme_name": "资源安全",
        "description": "磷矿 + 磷肥/磷化工,核心是磷矿品位与储量",
        "first_principle_variable": "磷矿品位/储量",
        "power_tier_baseline": 2,
        "thesis_variables": [
            {"name": "磷矿价格", "unit": "元/吨", "source": "manual"},
            {"name": "磷矿石自给率", "unit": "%", "source": "manual"},
            {"name": "磷酸一铵价格", "unit": "元/吨", "source": "manual"},
        ],
        "lixinger_industries": ["化学原料", "化学制品"],
        "source_ref": "invest2 BTGF/CHGF; invest3 §12",
    },
    {
        "name": "钾肥",
        "theme_name": "资源安全",
        "description": "钾肥资源股,核心是钾肥价格与品位",
        "first_principle_variable": "钾肥价格 × 矿石品位",
        "power_tier_baseline": 2,
        "thesis_variables": [
            {"name": "氯化钾售价", "unit": "元/吨", "source": "manual"},
            {"name": "钾矿品位", "unit": "%", "source": "manual"},
            {"name": "产能", "unit": "万吨", "source": "manual"},
        ],
        "lixinger_industries": ["化学原料", "化学制品"],
        "source_ref": "invest3 §12",
    },
    {
        "name": "铜矿",
        "theme_name": "资源安全",
        "description": "铜矿资源股,核心是铜价 × 储量",
        "first_principle_variable": "铜价 × 储量",
        "power_tier_baseline": 2,
        "thesis_variables": [
            {"name": "铜价", "unit": "元/吨", "source": "manual"},
            {"name": "铜储量", "unit": "万吨", "source": "manual"},
            {"name": "单位采铜成本", "unit": "元/吨", "source": "manual"},
        ],
        "lixinger_industries": ["工业金属", "有色金属"],
        "source_ref": "invest3 §12",
    },
    {
        "name": "锡矿",
        "theme_name": "资源安全",
        "description": "锡矿资源股(稀缺金属)",
        "first_principle_variable": "锡价 × 储量",
        "power_tier_baseline": 2,
        "thesis_variables": [
            {"name": "锡价", "unit": "元/吨", "source": "manual"},
            {"name": "锡储量", "unit": "万吨", "source": "manual"},
            {"name": "单位采锡成本", "unit": "元/吨", "source": "manual"},
        ],
        "lixinger_industries": ["有色金属"],
        "source_ref": "invest3 §12",
    },
    {
        "name": "黄金矿企",
        "theme_name": "金融安全",
        "description": "黄金矿企(藏金于国的资源端)",
        "first_principle_variable": "储量 × 金价 - 单位采金成本",
        "power_tier_baseline": 2,
        "thesis_variables": [
            {"name": "金均价", "unit": "元/克", "source": "manual"},
            {"name": "金储量", "unit": "吨", "source": "manual"},
            {"name": "单位采金成本", "unit": "元/克", "source": "manual"},
        ],
        "lixinger_industries": ["黄金", "有色金属"],
        "source_ref": "invest3 §12",
    },
    # ── 金融安全 (id=3) ─────────────────────────────────────────────
    {
        "name": "黄金零售",
        "theme_name": "金融安全",
        "description": "黄金珠宝零售(菜百模式),核心是金价 × 成交量",
        "first_principle_variable": "金价 × 成交量",
        "power_tier_baseline": 1,
        "thesis_variables": [
            {"name": "全球央行净买入", "unit": "吨", "source": "manual"},
            {"name": "上海金交所金价", "unit": "元/克", "source": "manual"},
            {"name": "门店数量", "unit": "家", "source": "manual"},
        ],
        "lixinger_industries": ["珠宝首饰", "零售"],
        "source_ref": "invest2 菜百",
    },
    {
        "name": "银行",
        "theme_name": "金融安全",
        "description": "盲盒可视化:不看不良率,看股息 + 地域 + 现金流匹配",
        "first_principle_variable": "股息 + 地域 + 长周期现金流/净利润匹配",
        "power_tier_baseline": 1,
        "thesis_variables": [
            {"name": "不良贷款率", "unit": "%", "source": "lixinger"},
            {"name": "拨备覆盖率", "unit": "%", "source": "lixinger"},
            {"name": "净息差", "unit": "%", "source": "lixinger"},
            {"name": "核心一级资本充足率", "unit": "%", "source": "lixinger"},
        ],
        "lixinger_industries": ["银行", "bank"],
        "source_ref": "invest3 §11 盲盒可视化",
    },
    {
        "name": "保险",
        "theme_name": "金融安全",
        "description": "保险股(资产配置层)",
        "first_principle_variable": "内含价值与新业务价值",
        "power_tier_baseline": 1,
        "thesis_variables": [
            {"name": "内含价值", "unit": "亿元", "source": "manual"},
            {"name": "新业务价值", "unit": "亿元", "source": "manual"},
            {"name": "综合成本率", "unit": "%", "source": "manual"},
        ],
        "lixinger_industries": ["保险", "保险Ⅱ", "insurance"],
        "source_ref": "invest3 §23 资产配置",
    },
    {
        "name": "证券",
        "theme_name": "金融安全",
        "description": "券商(资产配置层,与市场活跃度强相关)",
        "first_principle_variable": "日均股基交易量",
        "power_tier_baseline": 1,
        "thesis_variables": [
            {"name": "日均股基交易量", "unit": "亿元", "source": "manual"},
            {"name": "自营收益", "unit": "亿元", "source": "manual"},
            {"name": "投行业务收入", "unit": "亿元", "source": "manual"},
        ],
        "lixinger_industries": ["证券", "证券Ⅱ", "security"],
        "source_ref": "invest3 §23 资产配置",
    },
    # ── 能源安全 (id=1) ─────────────────────────────────────────────
    {
        "name": "电力",
        "theme_name": "能源安全",
        "description": "电力公用事业(基础生产资料)",
        "first_principle_variable": "利用小时数 × 上网电价",
        "power_tier_baseline": 2,
        "thesis_variables": [
            {"name": "利用小时数", "unit": "小时", "source": "manual"},
            {"name": "上网电价", "unit": "元/度", "source": "manual"},
            {"name": "装机容量", "unit": "GW", "source": "manual"},
        ],
        "lixinger_industries": ["电力", "电力Ⅱ"],
        "source_ref": "invest3 §13 公用事业",
    },
    # ── 粮食安全 (id=4) ─────────────────────────────────────────────
    {
        "name": "植物生长剂",
        "theme_name": "粮食安全",
        "description": "农药/植物生长调节剂(增效逻辑)",
        "first_principle_variable": "农资涨价下的增效需求",
        "power_tier_baseline": 1,
        "thesis_variables": [
            {"name": "农资价格指数", "unit": "", "source": "manual"},
            {"name": "主营产品均价", "unit": "元/吨", "source": "manual"},
            {"name": "经销商数量", "unit": "家", "source": "manual"},
        ],
        "lixinger_industries": ["农药", "农化制品"],
        "source_ref": "invest2 GGGF",
    },
    # ── 民生主线 (B3: theme_id 不再 null) ─────────────────────────────
    {
        "name": "药店零售",
        "theme_name": "民生",
        "description": "药店规模效应(老龄化 + 行业出清)",
        "first_principle_variable": "加盟店增速",
        "power_tier_baseline": 2,
        "thesis_variables": [
            {"name": "门店数量", "unit": "家", "source": "manual"},
            {"name": "同店增长率", "unit": "%", "source": "manual"},
            {"name": "处方外配比例", "unit": "%", "source": "manual"},
        ],
        "lixinger_industries": ["医药商业", "医药流通"],
        "source_ref": "invest2 DSL",
    },
    {
        "name": "旅游景区",
        "theme_name": "民生",
        "description": "低成本多巴胺(寺庙游/索道),数人头生意",
        "first_principle_variable": "客流 × 索道票均价",
        "power_tier_baseline": 2,
        "thesis_variables": [
            {"name": "客流量", "unit": "万人次", "source": "manual"},
            {"name": "索道票均价", "unit": "元/张", "source": "manual"},
            {"name": "客单价", "unit": "元/人", "source": "manual"},
        ],
        "lixinger_industries": ["旅游零售", "酒店餐饮", "景点"],
        "source_ref": "invest2 九华旅游",
    },
]


# ── Builtin plans ────────────────────────────────────────────────────
# strategy_ids resolved dynamically by slug after seeding strategies
#
# 止盈规则说明 (D7 — 2026-06-17 invest-alignment audit):
#   invest1 §13 原文是"**新手**可以设 30% 左右作为基本止盈线",
#   言下之意: 老手可按标的性质调整。各 plan 选择理由:
#     - core_value 30%:    严格贴 invest1 §13 新手基础值
#     - resource_macro 50%: 资源股周期弹性大 (铜/铝/磷肥常超 50%)
#     - bank_anchor DYR≤3%: invest2 §8 更高级 ("用股息率做买卖决策")
#     - contrarian_scan 无交易规则: 纯筛选, 留给用户判断
#   强行统一反而偏离 invest1/2 分类施策思想。
#
# 中游非 cost_leader 排除 (D6-B):
#   invest2 §13 三类禁投之一。已通过 plan_runner._should_filter_as_midstream_non_leader
#   实现,4 plan 默认 disable_midstream_filter=False 即 filter 启用。
#   BFNY/NSLY 等成本龙头 (Stock.is_cost_leader=True) 不受影响。

BUILTIN_PLANS = [
    {
        "slug": "core_value",
        "name": "核心价值配置",
        "description": "高股息安全垫 + 低估值买入信号，全市场扫描，分批建仓/30%止盈",
        "strategy_slugs": ["high_dividend_cushion", "undervalued_entry"],
        "logic": "AND",
        "scan_scope": {"type": "all_stocks", "values": []},
        "schedule_cron": "0 18 * * 1-5",
        "trading_rules": {
            "buy_ladder": [
                {"trigger": {"kind": "dyr_fwd_ge", "value": 0.05}, "add_pct": 0.3},
                {"trigger": {"kind": "pe_pct_le", "value": 0.20}, "add_pct": 0.3},
            ],
            "sell_ladder": [
                {"trigger": {"kind": "profit_pct_ge", "value": 0.30}, "reduce_pct_of_position": 0.5},
            ],
            "invalidation": [],
            "cooldown_days": 5,
        },
    },
    {
        "slug": "resource_macro",
        "name": "高息低估值",
        "description": "高股息 + 低估值 + 现金流安全垫",
        "strategy_slugs": ["resource_hard_asset", "high_dividend_cushion"],
        "logic": "AND",
        "scan_scope": {"type": "all_stocks", "values": []},
        "schedule_cron": "0 18 * * 1-5",
        "trading_rules": {
            "buy_ladder": [
                {"trigger": {"kind": "dyr_fwd_ge", "value": 0.04}, "add_pct": 0.25},
                {"trigger": {"kind": "price_le", "value": 0.8}, "add_pct": 0.25},
            ],
            "sell_ladder": [
                {"trigger": {"kind": "profit_pct_ge", "value": 0.50}, "reduce_pct_of_position": 0.5},
            ],
            "invalidation": [],
            "cooldown_days": 10,
        },
    },
    {
        "slug": "bank_anchor",
        "name": "银行底仓",
        "description": "银行业精选，DYR触发的买卖策略",
        "strategy_slugs": ["bank_select"],
        "logic": "AND",
        "scan_scope": {"type": "industries", "values": ["银行", "bank"]},
        "schedule_cron": "0 18 * * 1-5",
        "trading_rules": {
            "buy_ladder": [
                {"trigger": {"kind": "dyr_fwd_ge", "value": 0.06}, "add_pct": 0.3},
                {"trigger": {"kind": "pe_pct_le", "value": 0.25}, "add_pct": 0.3},
            ],
            "sell_ladder": [
                {"trigger": {"kind": "dyr_fwd_le", "value": 0.03}, "reduce_pct_of_position": 0.5},
            ],
            "invalidation": [],
            "cooldown_days": 7,
        },
    },
    {
        "slug": "contrarian_scan",
        "name": "超跌逆向",
        "description": "超跌逆向机会 + 现金流资产，纯筛选无交易规则",
        "strategy_slugs": ["contrarian_oversold", "cashflow_asset"],
        "logic": "AND",
        "scan_scope": {"type": "all_stocks", "values": []},
        "schedule_cron": "0 18 * * 1-5",
        "trading_rules": None,
    },
]


def seed_default_fee_config(db: Session) -> bool:
    """Insert default A-share fee config if not present.

    Rates current as of 2023-10-23 (stamp duty cut to 0.05% sell-only).
    User can edit via UI (S1.9) or add historical configs for backfill.
    Returns True if a new row was inserted.
    """
    existing = db.execute(
        select(BrokerFeeConfig).where(BrokerFeeConfig.broker_name == "default")
    ).scalar_one_or_none()
    if existing:
        return False  # idempotent

    db.add(
        BrokerFeeConfig(
            broker_name="default",
            commission_rate=0.00025,
            commission_min=5.0,
            stamp_duty_rate=0.0005,
            transfer_fee_rate=0.00001,
            effective_from=date(2023, 10, 23),
            is_active=True,
        )
    )
    db.flush()
    logger.info("Seeded default broker_fee_config (effective 2023-10-23)")
    return True


def seed_strategies(db: Session) -> int:
    """Seed or update built-in strategies. Returns count of newly inserted."""
    inserted = 0
    updated = 0
    for spec in BUILTIN_STRATEGIES:
        existing = db.execute(
            select(Strategy).where(Strategy.slug == spec["slug"])
        ).scalar_one_or_none()
        new_rule = json.dumps(spec["rule"], ensure_ascii=False)
        if existing is not None:
            if existing.rule_json != new_rule:
                existing.rule_json = new_rule
                existing.name = spec["name"]
                existing.description = spec["description"]
                updated += 1
            continue
        strategy = Strategy(
            name=spec["name"],
            slug=spec["slug"],
            description=spec["description"],
            kind="builtin",
            rule_json=new_rule,
            is_builtin=True,
        )
        db.add(strategy)
        inserted += 1
    if inserted or updated:
        db.flush()
        logger.info("Seeded %d built-in strategies, updated %d", inserted, updated)
    return inserted


def seed_plans(db: Session) -> int:
    """Seed or update built-in plans. Returns count of newly inserted."""
    inserted = 0
    updated = 0
    for spec in BUILTIN_PLANS:
        existing = db.execute(
            select(Plan).where(Plan.slug == spec["slug"])
        ).scalar_one_or_none()

        # Resolve strategy IDs by slug
        strategy_ids = []
        for slug in spec["strategy_slugs"]:
            s = db.execute(
                select(Strategy).where(Strategy.slug == slug)
            ).scalar_one_or_none()
            if s:
                strategy_ids.append(s.id)

        new_scope = json.dumps(spec["scan_scope"])
        new_comp = json.dumps({
            "strategy_ids": strategy_ids,
            "logic": spec["logic"],
        })
        new_tr = (
            json.dumps(spec["trading_rules"]) if spec.get("trading_rules") else None
        )

        if existing is not None:
            changed = False
            if existing.scan_scope_json != new_scope:
                existing.scan_scope_json = new_scope
                changed = True
            if existing.strategy_composition_json != new_comp:
                existing.strategy_composition_json = new_comp
                changed = True
            if existing.name != spec["name"]:
                existing.name = spec["name"]
                changed = True
            if existing.description != spec["description"]:
                existing.description = spec["description"]
                changed = True
            if existing.trading_rules_json != new_tr:
                existing.trading_rules_json = new_tr
                changed = True
            if changed:
                updated += 1
            continue

        plan = Plan(
            name=spec["name"],
            slug=spec["slug"],
            description=spec["description"],
            status="active",
            strategy_composition_json=new_comp,
            scan_scope_json=new_scope,
            schedule_cron=spec["schedule_cron"],
            trading_rules_json=(
                json.dumps(spec["trading_rules"]) if spec["trading_rules"] else None
            ),
            is_builtin=True,
        )
        db.add(plan)
        inserted += 1
    if inserted or updated:
        db.flush()
        logger.info("Seeded %d built-in plans, updated %d", inserted, updated)
    return inserted


def seed_business_patterns(db: Session) -> int:
    """Seed or update built-in business patterns. Returns count of newly inserted.

    Idempotent: matches by name. For existing builtin rows, updates methodology
    fields (first_principle_variable / power_tier_baseline / thesis_variables_json /
    lixinger_industries_json / source_ref / theme_id) but preserves user-edited
    description. User-created (is_builtin=False) rows are never touched here.
    """
    # Build theme name → id lookup
    theme_id_by_name: dict[str | None, int | None] = {None: None}
    for t in db.execute(select(Theme)).scalars():
        theme_id_by_name[t.name] = t.id

    inserted = 0
    updated = 0
    for spec in BUILTIN_BUSINESS_PATTERNS:
        existing = db.execute(
            select(BusinessPattern).where(BusinessPattern.name == spec["name"])
        ).scalar_one_or_none()

        theme_id = theme_id_by_name.get(spec.get("theme_name"))
        new_tv = json.dumps(spec.get("thesis_variables", []), ensure_ascii=False)
        new_li = json.dumps(spec.get("lixinger_industries", []), ensure_ascii=False)

        if existing is not None:
            if not existing.is_builtin:
                continue  # never overwrite user-created
            # Refresh methodology fields, preserve user-edited description
            changed = False
            if existing.first_principle_variable != spec.get("first_principle_variable"):
                existing.first_principle_variable = spec.get("first_principle_variable")
                changed = True
            if existing.power_tier_baseline != spec["power_tier_baseline"]:
                existing.power_tier_baseline = spec["power_tier_baseline"]
                changed = True
            if existing.thesis_variables_json != new_tv:
                existing.thesis_variables_json = new_tv
                changed = True
            if existing.lixinger_industries_json != new_li:
                existing.lixinger_industries_json = new_li
                changed = True
            if existing.source_ref != spec.get("source_ref"):
                existing.source_ref = spec.get("source_ref")
                changed = True
            if existing.theme_id != theme_id:
                existing.theme_id = theme_id
                changed = True
            # G2: is_midstream sync
            spec_midstream = bool(spec.get("is_midstream", False))
            if existing.is_midstream != spec_midstream:
                existing.is_midstream = spec_midstream
                changed = True
            if changed:
                updated += 1
            continue

        bp = BusinessPattern(
            name=spec["name"],
            theme_id=theme_id,
            description=spec.get("description"),
            first_principle_variable=spec.get("first_principle_variable"),
            power_tier_baseline=spec["power_tier_baseline"],
            is_midstream=bool(spec.get("is_midstream", False)),
            thesis_variables_json=new_tv,
            lixinger_industries_json=new_li,
            source_ref=spec.get("source_ref"),
            is_builtin=True,
        )
        db.add(bp)
        inserted += 1

    if inserted or updated:
        db.flush()
        logger.info(
            "Seeded %d builtin business patterns, updated %d", inserted, updated
        )
    return inserted


# ── G2 cost leaders (invest3 §12 显式案例) ────────────────────────────
# invest docs 反复强调的资源股 cost_leader — seeder 启动时预填,用户 override 其他股票.
# Map stock_code → True (is_cost_leader).
BUILTIN_COST_LEADERS: dict[str, bool] = {
    "600989": True,  # 宝丰能源 (BFNY) — 煤化工,自给煤矿+技术路线领先
    "600219": True,  # 南山铝业 (NSLY) — 电解铝,印尼电力套利
}


def seed_cost_leaders(db: Session) -> int:
    """G2: pre-fill Stock.is_cost_leader=True for known cost-leader codes.

    Idempotent — only sets True for codes in BUILTIN_COST_LEADERS that
    already exist in stocks table. Leaves other stocks untouched (user
    can manually mark them via UI/PATCH).
    """
    updated = 0
    for code, val in BUILTIN_COST_LEADERS.items():
        existing = db.get(Stock, code)
        if existing is None:
            continue  # stock not synced yet; skip silently
        if existing.is_cost_leader != val:
            existing.is_cost_leader = val
            updated += 1
    if updated:
        db.flush()
        logger.info("Seeded %d cost-leader overrides", updated)
    return updated


# ── G4 resource leaders (invest3 §12 显式案例) ────────────────────────
# invest docs 反复强调的"有矿 + 国内优先"资源股 — seeder 启动时预填.
# Map stock_code → {has_mine, domestic_leader, expansion_outlook, geo_risk}.
# B2: 后 2 字段对 7 个公开案例都标 True (均为稳定扩产 + 地缘风险可控的龙头).
BUILTIN_RESOURCE_LEADERS: dict[str, dict[str, bool]] = {
    "600989": {"has_mine": True, "domestic_leader": True, "expansion_outlook": True, "geo_risk": True},  # 宝丰能源 (BFNY) 煤化工
    "600219": {"has_mine": True, "domestic_leader": True, "expansion_outlook": True, "geo_risk": True},  # 南山铝业 (NSLY) 电解铝
    "002170": {"has_mine": True, "domestic_leader": True, "expansion_outlook": True, "geo_risk": True},  # 芭田股份 (BTGF) 磷矿
    "002895": {"has_mine": True, "domestic_leader": True, "expansion_outlook": True, "geo_risk": True},  # 川恒股份 (CHGF) 磷化工
    "601899": {"has_mine": True, "domestic_leader": True, "expansion_outlook": True, "geo_risk": True},  # 紫金矿业 铜/金/锌
    "600547": {"has_mine": True, "domestic_leader": True, "expansion_outlook": True, "geo_risk": True},  # 山东黄金 金矿
    "600489": {"has_mine": True, "domestic_leader": True, "expansion_outlook": True, "geo_risk": True},  # 中金黄金 金矿
}


def seed_resource_leaders(db: Session) -> int:
    """G4 + B2: pre-fill Stock resource flags for known leaders.

    Idempotent — only updates rows that already exist in stocks table.
    """
    updated = 0
    for code, flags in BUILTIN_RESOURCE_LEADERS.items():
        existing = db.get(Stock, code)
        if existing is None:
            continue
        changed = False
        for field in ("has_mine", "domestic_leader", "expansion_outlook", "geo_risk"):
            if getattr(existing, field) != flags[field]:
                setattr(existing, field, flags[field])
                changed = True
        if changed:
            updated += 1
    if updated:
        db.flush()
        logger.info("Seeded %d resource-leader overrides", updated)
    return updated


def seed_all(db: Session) -> dict:
    """Seed all built-in data. Called from main.py lifespan."""
    f = seed_default_fee_config(db)
    s = seed_strategies(db)
    p = seed_plans(db)
    t = seed_all_years(db)
    bp = seed_business_patterns(db)
    cl = seed_cost_leaders(db)
    rl = seed_resource_leaders(db)
    db.commit()
    return {
        "fee_config_inserted": f,
        "strategies": s,
        "plans": p,
        "trading_calendar_inserted": t,
        "business_patterns": bp,
        "cost_leaders": cl,
        "resource_leaders": rl,
    }
