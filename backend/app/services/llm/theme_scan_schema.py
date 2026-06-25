"""JSON schemas for theme_scan_pipeline output (serenity engine).

5-step workflow (trading-philosophy.md §2, serenity SKILL.md):
  1. system_change   叙事 → 系统变化 + 关键物理/经济约束
  2. value_chain     产业链分层
  3. scarce_layer    稀缺层排序 (serenity 核心动作: 先排层级再排公司)
  4. company_universe A 股公司宇宙 (提议真实 A 股代码, 后续校验)
  5. candidate_rank   候选打分排序 (每家: chain_position + scarcity_score + 失败条件)
"""
from __future__ import annotations

from app.services.llm.deep_research_schema import EVIDENCE_ITEM


# Step 1: 叙事 → 系统变化
SYSTEM_CHANGE_SCHEMA = {
    "type": "object",
    "properties": {
        "theme": {"type": "string"},
        "system_change": {"type": "string", "description": "驱动需求的技术/经济变化"},
        "key_constraint": {
            "type": "string",
            "description": "最关键的物理/经济约束",
            "enum": ["power", "latency", "bandwidth", "heat", "yield", "purity",
                     "reliability", "cycle_time", "packaging_density", "regulation",
                     "grid_connection", "other"],
        },
        "demand_drivers": {"type": "array", "items": {"type": "string"}},
        "strained_old_design": {"type": "string", "description": "哪种旧设计被绷紧"},
    },
    "required": ["theme", "system_change", "key_constraint"],
}


# Step 2: 产业链分层
VALUE_CHAIN_SCHEMA = {
    "type": "object",
    "properties": {
        "layers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "role": {"type": "string", "description": "该层在产业链中的作用"},
                    "examples": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "role"],
            },
        },
    },
    "required": ["layers"],
}


# Step 3: 稀缺层排序 (serenity 核心)
SCARCE_LAYER_SCHEMA = {
    "type": "object",
    "properties": {
        "ranked_layers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "layer": {"type": "string"},
                    "rank": {"type": "integer", "minimum": 1},
                    "scarcity_signals": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "低供应商数/长认证/难扩产/关键know-how/高纯度/客户认证/长交期/产能预订",
                    },
                    "scarcity_rationale": {"type": "string"},
                },
                "required": ["layer", "rank", "scarcity_rationale"],
            },
        },
        "lower_ranked_obvious_layer": {
            "type": "string",
            "description": "一个热门但排名靠后的层级 + 为什么靠后 (serenity 要求)",
        },
    },
    "required": ["ranked_layers"],
}


# Step 4: A 股公司宇宙 (提议代码, 后续校验)
COMPANY_UNIVERSE_SCHEMA = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "A 股 6 位代码"},
                    "name": {"type": "string"},
                    "layer": {"type": "string", "description": "所属产业链层级"},
                    "classification": {
                        "type": "string",
                        "enum": ["controls", "supplies", "benefits", "weak", "story"],
                        "description": "controls=控制稀缺层 / supplies=供应稀缺层 / benefits=受益 / weak=弱控制 / story=仅有故事",
                    },
                    "note": {"type": "string"},
                },
                "required": ["code", "name", "layer", "classification"],
            },
        },
    },
    "required": ["candidates"],
}


# Step 5: 候选打分排序
CANDIDATE_RANK_SCHEMA = {
    "type": "object",
    "properties": {
        "ranked": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "name": {"type": "string"},
                    "layer": {"type": "string"},
                    "chain_position": {
                        "type": "string",
                        "enum": ["controls", "supplies", "benefits", "weak", "story"],
                    },
                    "scarcity_score": {
                        "type": "number", "minimum": 1.0, "maximum": 5.0,
                        "description": "卡点强度 1-5，交给 deep_research 作 scarcity 维度",
                    },
                    "thesis": {"type": "string", "description": "5 句内卡点逻辑"},
                    "failure_conditions": {
                        "type": "array", "items": {"type": "string"},
                        "description": "什么情况说明判断错了: 替代/对手扩产/需求转弱/稀释/毛利恶化/治理/客户流失/估值已price in",
                    },
                    "evidence": {"type": "array", "items": EVIDENCE_ITEM},
                },
                "required": ["code", "name", "layer", "chain_position", "scarcity_score", "thesis"],
            },
        },
        "evidence_grade": {"type": "string", "enum": ["A", "B", "C"]},
        "markdown_report": {"type": "string", "description": "serenity 风格主题报告"},
    },
    "required": ["ranked"],
}
