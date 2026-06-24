"""JSON schemas for deep_research_pipeline output.

Each step's `response_schema` is used as the `submit_result` function's
`parameters` in Zhipu tool_use. LLM is forced to call this tool to return
structured output.
"""
from __future__ import annotations


# Common evidence sub-schema (reused across all master outputs)
EVIDENCE_ITEM = {
    "type": "object",
    "properties": {
        "claim": {"type": "string", "description": "具体声明"},
        "source_url": {"type": "string", "description": "来源 URL（web_search 结果中）"},
        "source_type": {
            "type": "string",
            "enum": ["filing", "exchange", "ir", "transcript", "regulator",
                     "patent", "standard", "order", "media", "research", "social"],
        },
        "grade": {"type": "string", "enum": ["strong", "medium", "weak", "unverified_lead"]},
        "verified_at": {"type": "string", "description": "ISO timestamp"},
    },
    "required": ["claim", "grade"],
}


# Step 1: data_collection
DATA_COLLECTION_SCHEMA = {
    "type": "object",
    "properties": {
        "stock_code": {"type": "string"},
        "info_grade": {"type": "string", "enum": ["A", "B", "C"]},
        "data_conflicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string"},
                    "lixinger": {},
                    "web_search": {},
                    "diff_pct": {"type": "number"},
                },
                "required": ["field"],
            },
        },
        "key_numbers": {
            "type": "object",
            "properties": {
                "market_cap_yi": {"type": "number"},
                "pe_ttm": {"type": "number"},
                "pb": {"type": "number"},
                "roe_pct": {"type": "number"},
                "revenue_yi": {"type": "number"},
                "net_profit_yi": {"type": "number"},
                "ocf_yi": {"type": "number"},
                "dividend_yield_pct": {"type": "number"},
                "gross_margin_pct": {"type": "number"},
                "net_margin_pct": {"type": "number"},
            },
        },
        "recent_events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "date": {"type": "string"},
                    "type": {"type": "string", "enum": ["announcement", "news", "research", "filing"]},
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "sentiment": {"type": "string", "enum": ["positive", "neutral", "negative"]},
                    "source_url": {"type": "string"},
                },
                "required": ["title", "summary"],
            },
        },
        "key_questions": {
            "type": "array",
            "items": {"type": "string"},
        },
        "data_limitations": {"type": "string"},
    },
    "required": ["stock_code", "info_grade", "key_numbers", "recent_events", "key_questions"],
}


# Step 2a: 段永平
DUAN_MASTER_SCHEMA = {
    "type": "object",
    "properties": {
        "master": {"type": "string", "enum": ["duan"]},
        "business_essence": {"type": "string"},
        "is_good_business": {"type": "boolean"},
        "good_business_reasons": {"type": "array", "items": {"type": "string"}},
        "bad_business_reasons": {"type": "array", "items": {"type": "string"}},
        "circle_of_competence": {"type": "string", "enum": ["in", "out", "unclear"]},
        "circle_reasoning": {"type": "string"},
        "mirror_test_passed": {"type": "boolean"},
        "mirror_test_statement": {"type": "string"},
        "score": {"type": "number", "minimum": 1.0, "maximum": 5.0},
        "score_justification": {"type": "string"},
        "key_risks": {"type": "array", "items": {"type": "string"}},
        "evidence": {"type": "array", "items": EVIDENCE_ITEM},
        "quote": {"type": "string"},
    },
    "required": ["master", "business_essence", "is_good_business", "score", "score_justification", "key_risks"],
}


# Step 2b: 巴菲特
BUFFETT_MASTER_SCHEMA = {
    "type": "object",
    "properties": {
        "master": {"type": "string", "enum": ["buffett"]},
        "moat_types": {
            "type": "array",
            "items": {"type": "string", "enum": ["brand", "network_effect", "cost", "switching_cost", "regulatory", "intangible", "none"]},
        },
        "moat_strength": {"type": "string", "enum": ["wide", "narrow", "none"]},
        "moat_trend": {"type": "string", "enum": ["widening", "stable", "narrowing"]},
        "moat_evidence": {"type": "array", "items": EVIDENCE_ITEM},
        "management_quality": {
            "type": "object",
            "properties": {
                "integrity": {"type": "string", "enum": ["high", "medium", "low"]},
                "capital_allocation": {"type": "string", "enum": ["high", "medium", "low"]},
                "compensation_reasonable": {"type": "boolean"},
                "insider_buying": {"type": "boolean"},
                "evidence": {"type": "array", "items": EVIDENCE_ITEM},
            },
        },
        "valuation": {
            "type": "object",
            "properties": {
                "current_pe": {"type": "number"},
                "pe_percentile_10y": {"type": "number"},
                "dcf_intrinsic_value_yi": {"type": "number"},
                "scenarios": {
                    "type": "object",
                    "properties": {
                        "optimistic": {
                            "type": "object",
                            "properties": {
                                "target_price": {"type": "number"},
                                "assumption": {"type": "string"},
                            },
                        },
                        "neutral": {
                            "type": "object",
                            "properties": {
                                "target_price": {"type": "number"},
                                "assumption": {"type": "string"},
                            },
                        },
                        "pessimistic": {
                            "type": "object",
                            "properties": {
                                "target_price": {"type": "number"},
                                "assumption": {"type": "string"},
                            },
                        },
                    },
                },
                "margin_of_safety_pct": {"type": "number"},
            },
        },
        "score": {"type": "number", "minimum": 1.0, "maximum": 5.0},
        "score_justification": {"type": "string"},
        "key_risks": {"type": "array", "items": {"type": "string"}},
        "evidence": {"type": "array", "items": EVIDENCE_ITEM},
        "quote": {"type": "string"},
    },
    "required": ["master", "moat_types", "moat_strength", "moat_trend", "score", "score_justification", "key_risks"],
}


# Step 2c: 芒格
MUNGER_MASTER_SCHEMA = {
    "type": "object",
    "properties": {
        "master": {"type": "string", "enum": ["munger"]},
        "failure_scenarios": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "scenario": {"type": "string"},
                    "probability": {"type": "string", "enum": ["high", "medium", "low"]},
                    "trigger_signals": {"type": "array", "items": {"type": "string"}},
                    "estimated_downside_pct": {"type": "number"},
                    "evidence": {"type": "array", "items": EVIDENCE_ITEM},
                },
                "required": ["scenario", "probability"],
            },
        },
        "cognitive_biases_checked": {
            "type": "object",
            "properties": {
                "anchoring": {"type": "string"},
                "narrative": {"type": "string"},
                "confirmation": {"type": "string"},
                "herding": {"type": "string"},
            },
        },
        "consensus_aligned": {"type": "boolean"},
        "contrarian_view": {"type": "string"},
        "mental_models_applied": {"type": "array", "items": {"type": "string"}},
        "score": {"type": "number", "minimum": 1.0, "maximum": 5.0},
        "score_justification": {"type": "string"},
        "key_risks": {"type": "array", "items": {"type": "string"}},
        "evidence": {"type": "array", "items": EVIDENCE_ITEM},
        "quote": {"type": "string"},
    },
    "required": ["master", "failure_scenarios", "score", "score_justification", "key_risks"],
}


# Step 2d: 李录
LILU_MASTER_SCHEMA = {
    "type": "object",
    "properties": {
        "master": {"type": "string", "enum": ["lilu"]},
        "civilization_trend_fit": {"type": "string", "enum": ["strong", "medium", "weak", "against"]},
        "civilization_reasoning": {"type": "string"},
        "decade_certainty": {
            "type": "object",
            "properties": {
                "exists_in_10y": {"type": "string", "enum": ["high", "medium", "low"]},
                "business_model_valid_in_10y": {"type": "string", "enum": ["high", "medium", "low"]},
                "advantage_sustained_in_10y": {"type": "string", "enum": ["high", "medium", "low"]},
                "market_larger_in_10y": {"type": "string", "enum": ["high", "medium", "low"]},
            },
        },
        "compounding_characteristics": {
            "type": "object",
            "properties": {
                "high_roe_sustainable": {"type": "boolean"},
                "reinvestment_efficiency": {"type": "string", "enum": ["high", "medium", "low"]},
                "tam_expanding": {"type": "boolean"},
                "pricing_power": {"type": "boolean"},
                "evidence": {"type": "array", "items": EVIDENCE_ITEM},
            },
        },
        "china_specific_risks": {
            "type": "object",
            "properties": {
                "policy_risk": {"type": "string"},
                "going_global_ability": {"type": "string"},
                "domestic_substitution_play": {"type": "string", "enum": ["none", "passive", "active"]},
                "demographic_alignment": {"type": "string"},
            },
        },
        "score": {"type": "number", "minimum": 1.0, "maximum": 5.0},
        "score_justification": {"type": "string"},
        "key_risks": {"type": "array", "items": {"type": "string"}},
        "evidence": {"type": "array", "items": EVIDENCE_ITEM},
        "quote": {"type": "string"},
    },
    "required": ["master", "civilization_trend_fit", "decade_certainty", "score", "score_justification", "key_risks"],
}


# Step 3: Synthesis
SYNTHESIS_SCHEMA = {
    "type": "object",
    "properties": {
        "stock_code": {"type": "string"},
        "overall_score": {"type": "number", "minimum": 1.0, "maximum": 5.0},
        "recommendation": {"type": "string", "enum": ["BUY", "HOLD", "PASS"]},
        "master_scores": {
            "type": "object",
            "properties": {
                "duan": {"type": "number"},
                "buffett": {"type": "number"},
                "munger": {"type": "number"},
                "lilu": {"type": "number"},
            },
            "required": ["duan", "buffett", "munger", "lilu"],
        },
        "master_disagreements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "resolution": {"type": "string"},
                    "impact_on_score": {"type": "number"},
                },
            },
        },
        "price_ranges": {
            "type": "object",
            "properties": {
                "aggressive": {
                    "type": "object",
                    "properties": {
                        "min": {"type": "number"},
                        "max": {"type": "number"},
                        "rationale": {"type": "string"},
                    },
                },
                "steady": {
                    "type": "object",
                    "properties": {
                        "min": {"type": "number"},
                        "max": {"type": "number"},
                        "rationale": {"type": "string"},
                    },
                },
                "conservative": {
                    "type": "object",
                    "properties": {
                        "min": {"type": "number"},
                        "max": {"type": "number"},
                        "rationale": {"type": "string"},
                    },
                },
            },
        },
        "mirror_test": {
            "type": "object",
            "properties": {
                "passed": {"type": "boolean"},
                "statement": {"type": "string"},
            },
        },
        "red_line_flags": {
            "type": "object",
            "description": "Map of red_line_type → evidence. Empty/absent = no red lines.",
            "additionalProperties": {"type": "object"},
        },
        "evidence_grade": {"type": "string", "enum": ["A", "B", "C"]},
        "evidence_summary": {"type": "string"},
        "key_risks_prioritized": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "risk": {"type": "string"},
                    "probability": {"type": "string", "enum": ["high", "medium", "low"]},
                    "impact": {"type": "string", "enum": ["high", "medium", "low"]},
                },
            },
        },
        "next_checks_needed": {"type": "array", "items": {"type": "string"}},
        "markdown_report": {"type": "string", "description": "ai-berkshire 风格的完整 markdown 报告"},
    },
    "required": ["stock_code", "overall_score", "recommendation", "master_scores",
                 "mirror_test", "evidence_grade", "key_risks_prioritized", "markdown_report"],
}
