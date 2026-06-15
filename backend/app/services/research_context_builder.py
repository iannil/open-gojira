"""Build LLM context from Lixinger data.

Pulls industry constituents for the theme's keyword-matched industries.
Used to seed LLM with verified stock codes (reduce hallucination).
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.services.lixinger_client import get_lixinger_client

logger = logging.getLogger(__name__)


# Theme → SW industry keyword map (Lixinger SW 2021 source)
THEME_INDUSTRY_KEYWORDS: dict[str, list[str]] = {
    "AI 半导体": ["半导体", "集成电路", "消费电子", "光学光电子", "元件"],
    "半导体": ["半导体", "集成电路"],
    "资源": ["钢铁", "有色金属", "采掘", "化工"],
    "银行": ["银行"],
    "CPO": ["通信", "光学光电子", "半导体"],
    "光模块": ["通信", "光学光电子"],
    "机器人": ["通用设备", "专用设备", "自动化", "电机"],
    "HBM": ["半导体", "集成电路"],
}


def build_user_context(theme: str, market: str, time_window: str = "3-12M") -> str:
    """Build JSON context for LLM user message.

    On Lixinger failure, falls back to minimal context (theme only). The
    LLM can still produce a research via web_search alone.
    """
    try:
        lixinger = get_lixinger_client()
        industries = lixinger.get_industry_list(source="sw_2021")
        keywords = THEME_INDUSTRY_KEYWORDS.get(theme, [theme])
        matched = [
            ind for ind in industries
            if any(kw in ind.get("name", "") for kw in keywords)
        ][:5]

        candidates: list[dict[str, Any]] = []
        for ind in matched:
            try:
                constituents = lixinger.get_industry_constituents(ind["stockCode"])[:20]
                candidates.extend(constituents)
            except Exception as exc:
                logger.warning(
                    "Lixinger industry=%s constituents failed: %s",
                    ind.get("name"), exc,
                )

        def _extract_name(stock_name_obj: Any) -> str:
            if isinstance(stock_name_obj, dict):
                return (
                    stock_name_obj.get("cmn_hans_cn")
                    or stock_name_obj.get("en")
                    or ""
                )
            return str(stock_name_obj)

        snapshot = {
            "theme": theme,
            "market": market,
            "time_window": time_window,
            "candidates_hint": [
                {
                    "code": c.get("stockCode") or c.get("stock_code"),
                    "name": _extract_name(c.get("stockName") or c.get("name")),
                    "industry": ind.get("name"),
                }
                for c in candidates[:60]
            ],
            "instruction": (
                "以上是 Lixinger 行业成分股参考名单。你可以扩展或精简,"
                "但最终公司宇宙必须 ≥20 家,且覆盖稀缺层上下游。"
                "对每家公司,你必须通过 web_search 验证其在产业链中的位置和稀缺性证据,"
                "不要凭空判断。"
            ),
        }
        return json.dumps(snapshot, ensure_ascii=False, indent=2)
    except Exception as exc:
        logger.warning(
            "Lixinger context build failed (will fall back to LLM only): %s", exc
        )
        return json.dumps(
            {
                "theme": theme,
                "market": market,
                "time_window": time_window,
                "note": (
                    f"Lixinger 上下文构建失败: {exc}. "
                    "请直接基于 web_search 结果构建公司宇宙。"
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
