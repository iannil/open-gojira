"""Serenity research prompts and JSON schema.

Kept centralized so spike / production / tests share identical constraints.
"""
from __future__ import annotations

from typing import Any


def build_system_prompt(max_searches: int) -> str:
    """Serenity system prompt. Parameterized with current run limits."""
    return f"""你是 Gojira 投资驾驶舱的「供应链卡点猎手」研究助手,遵循 serenity-skill 方法论。

# 工作流

1. 把主题翻译为系统变化(一句话技术/经济变化)
2. 列价值链 8 层:
   - 1=下游客户 / 2=系统集成 / 3=模块子系统 / 4=芯片器件
   - 5=工艺封装测试 / 6=设备与计量 / 7=材料耗材 / 8=物理基建
3. 找稀缺层并排名 (3-5 层),每层带:rank / 推理(reason) / 扩产难度(high/medium/low)
4. 构建公司宇宙 (≥20 家 A 股),跨各层,每家带 classification:
   - controls(控制稀缺层) / supplies(供应稀缺层) / benefits(受益) / weak(弱定价权) / story(故事为主)
5. 收集证据 (≥25 sources,4 档分级):
   - strong: 年报/季报/公告/问询函/招投标/环评/专利/官方订单
   - medium: 公司 IR / 财报电话会议 / 权威财经媒体 / 行业期刊
   - weak: 行业协会 / 标准 / 技术论文 / 二手转述
   - lead: KOL / 社交媒体线索 (不作证明,仅作线索)
6. 选出 Top 3-7 公司,每家带 5 字段:
   - constrains_what(卡住的环节)
   - chain_position(产业链位置)
   - rank_reason(为什么排这里)
   - evidence_summary(证据摘要)
   - main_risk(主要风险)
7. 列失败条件 (≥3 条): 什么情况说明这个判断错了
8. 列下一步验证 (≥3 条): 用户该查什么具体文档/数据

# 强制约束

- 每条证据必须有 source_url (真实可访问)
- 未经 URL 验证的一律降为 lead
- **优先访问**: cninfo.com.cn / sse.com.cn / szse.cn / eastmoney.com / 同花顺 / 巨潮资讯
- 公司宇宙 ≥20 家,证据 ≥25 sources,任一不达标必须继续调用 web_search
- A 股代码 6 位数字(沪市 6 开头 / 深市 0/3 开头 / 北交所 8/4 开头)
- 输出严格按 submit_research 工具 schema,不要裸文本

# 工具

- web_search: 抓取实时数据 (上限 {max_searches} 次)
- submit_research: 提交结构化研究结果 (必须调用,且只调用一次)

开始工作。"""


SERENITY_RESEARCH_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "system_change",
        "value_chain",
        "scarce_layers",
        "company_universe",
        "evidence",
        "company_ranking",
        "failure_conditions",
        "next_steps",
    ],
    "properties": {
        "system_change": {
            "type": "string",
            "description": "一句话:技术/经济变化驱动需求",
        },
        "value_chain": {
            "type": "array",
            "minItems": 8,
            "maxItems": 8,
            "description": "价值链 8 层",
            "items": {
                "type": "object",
                "required": ["layer_index", "name", "description"],
                "properties": {
                    "layer_index": {"type": "integer", "minimum": 1, "maximum": 8},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                },
            },
        },
        "scarce_layers": {
            "type": "array",
            "minItems": 3,
            "maxItems": 5,
            "description": "稀缺层排名 (3-5 层)",
            "items": {
                "type": "object",
                "required": ["rank", "layer_index", "reason", "difficulty"],
                "properties": {
                    "rank": {"type": "integer", "minimum": 1},
                    "layer_index": {"type": "integer", "minimum": 1, "maximum": 8},
                    "reason": {"type": "string"},
                    "difficulty": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                    },
                },
            },
        },
        "company_universe": {
            "type": "array",
            "minItems": 20,
            "description": "公司宇宙 ≥20 家",
            "items": {
                "type": "object",
                "required": ["stock_code", "name", "classification"],
                "properties": {
                    "stock_code": {"type": "string", "pattern": r"^\d{6}$"},
                    "name": {"type": "string"},
                    "classification": {
                        "type": "string",
                        "enum": [
                            "controls", "supplies", "benefits", "weak", "story",
                        ],
                    },
                    "layer_index": {"type": "integer", "minimum": 1, "maximum": 8},
                    "note": {"type": "string"},
                },
            },
        },
        "evidence": {
            "type": "array",
            "minItems": 25,
            "description": "证据 ≥25 sources",
            "items": {
                "type": "object",
                "required": [
                    "source_url", "source_title", "source_type", "grade", "summary",
                ],
                "properties": {
                    "stock_code": {"type": "string", "pattern": r"^\d{6}$"},
                    "source_url": {"type": "string"},
                    "source_title": {"type": "string"},
                    "source_type": {
                        "type": "string",
                        "enum": [
                            "filing", "announcement", "transcript", "patent",
                            "standard", "regulator_doc", "media", "trade_pub",
                            "social_lead",
                        ],
                    },
                    "published_at": {"type": "string", "format": "date"},
                    "grade": {
                        "type": "string",
                        "enum": ["strong", "medium", "weak", "lead"],
                    },
                    "summary": {"type": "string"},
                },
            },
        },
        "company_ranking": {
            "type": "array",
            "minItems": 3,
            "maxItems": 7,
            "description": "Top 3-7 公司排名",
            "items": {
                "type": "object",
                "required": [
                    "rank", "stock_code", "name", "constrains_what",
                    "chain_position", "rank_reason", "evidence_summary", "main_risk",
                ],
                "properties": {
                    "rank": {"type": "integer", "minimum": 1},
                    "stock_code": {"type": "string", "pattern": r"^\d{6}$"},
                    "name": {"type": "string"},
                    "constrains_what": {"type": "string"},
                    "chain_position": {"type": "string"},
                    "rank_reason": {"type": "string"},
                    "evidence_summary": {"type": "string"},
                    "main_risk": {"type": "string"},
                },
            },
        },
        "failure_conditions": {
            "type": "array",
            "minItems": 3,
            "items": {"type": "string"},
        },
        "next_steps": {
            "type": "array",
            "minItems": 3,
            "items": {"type": "string"},
        },
    },
}
