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
from app.models.plan import Plan
from app.models.strategy import Strategy

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
                {"field": "dyr", "op": ">=", "value": 0.04},
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
        "description": "高股息筛选（行业分类暂不可用，仅靠股息率筛选）",
        "rule": {
            "logic": "AND",
            "conditions": [
                {"field": "dyr", "op": ">=", "value": 0.04},
                {"field": "pb_pct_10y", "op": "<=", "value": 0.50},
            ],
        },
    },
    {
        "slug": "bank_select",
        "name": "银行业精选",
        "description": "银行行业、股息率≥5%",
        "rule": {
            "logic": "AND",
            "conditions": [
                {"field": "industry_in", "op": "in", "value": ["bank"]},
                {"field": "dyr", "op": ">=", "value": 0.05},
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
                {"field": "dyr", "op": ">=", "value": 0.04},
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
                {"field": "dyr", "op": ">=", "value": 0.04},
                {"field": "dividend_sustainability", "op": ">=", "value": 50},
            ],
        },
    },
]

# ── Builtin plans ────────────────────────────────────────────────────
# strategy_ids resolved dynamically by slug after seeding strategies

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
                {"trigger": {"kind": "dyr_ge", "value": 0.05}, "add_pct": 0.3},
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
                {"trigger": {"kind": "dyr_ge", "value": 0.04}, "add_pct": 0.25},
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
        "scan_scope": {"type": "industries", "values": ["bank"]},
        "schedule_cron": "0 18 * * 1-5",
        "trading_rules": {
            "buy_ladder": [
                {"trigger": {"kind": "dyr_ge", "value": 0.06}, "add_pct": 0.3},
                {"trigger": {"kind": "pe_pct_le", "value": 0.25}, "add_pct": 0.3},
            ],
            "sell_ladder": [
                {"trigger": {"kind": "dyr_le", "value": 0.03}, "reduce_pct_of_position": 0.5},
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


def seed_all(db: Session) -> dict:
    """Seed all built-in data. Called from main.py lifespan."""
    f = seed_default_fee_config(db)
    s = seed_strategies(db)
    p = seed_plans(db)
    db.commit()
    return {"fee_config_inserted": f, "strategies": s, "plans": p}
