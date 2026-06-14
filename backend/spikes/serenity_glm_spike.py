"""Spike: 验证 GLM + web_search 能否跑通 serenity-skill 完整工作流。

不入 app/, 不入测试。仅产出 demo JSON + Markdown 报告。

用法:
    # 1. 注册智谱开放平台账号,获取 API key: https://open.bigmodel.cn/usercenter/apikeys
    # 2. 加到 backend/.env:
    #    ZHIPU_API_KEY=<your-key>
    #    ZHIPU_MODEL=glm-4.7  # 或 glm-5.1 / glm-5.2 (GLM-5.2 API 已开放后)
    # 3. 跑 spike:
    cd backend && source .venv/bin/activate
    python spikes/serenity_glm_spike.py

输出:
    backend/spikes/output/serenity_demo.json
    backend/spikes/output/serenity_demo.md
    backend/spikes/output/serenity_stats.txt
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# 让 import app.* 能工作
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from zhipuai import ZhipuAI

load_dotenv(Path(__file__).parent.parent / ".env")

# ─── 配置 ────────────────────────────────────────────────────────────
ZHIPU_API_KEY = os.getenv("ZHIPU_API_KEY", "")
ZHIPU_MODEL = os.getenv("ZHIPU_MODEL", "glm-4.7")
MAX_TOKENS = int(os.getenv("SERENITY_MAX_TOKENS", "16000"))
MAX_SEARCHES = int(os.getenv("SERENITY_MAX_SEARCHES", "30"))
TIMEOUT_SEC = int(os.getenv("SERENITY_TIMEOUT", "300"))
THEME = os.getenv("SERENITY_THEME", "AI 半导体")
MARKET = os.getenv("SERENITY_MARKET", "A_SHARE")
TIME_WINDOW = os.getenv("SERENITY_TIME_WINDOW", "3-12M")

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


# ─── System prompt (复用 serenity-skill 方法论) ─────────────────────
SYSTEM_PROMPT = """你是 Gojira 投资驾驶舱的「供应链卡点猎手」研究助手,遵循 serenity-skill 方法论。

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

- web_search: 抓取实时数据 (上限 """ + str(MAX_SEARCHES) + """ 次)
- submit_research: 提交结构化研究结果 (必须调用,且只调用一次)

开始工作。"""


# ─── JSON Schema for submit_research tool ──────────────────────────
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


def build_user_context(theme: str, market: str) -> str:
    """从 Lixinger 拉行业成分股作为上下文,降低 LLM 幻觉。"""
    try:
        from app.services.lixinger_client import get_lixinger_client
        lixinger = get_lixinger_client()

        industries = lixinger.get_industry_list(source="sw_2021")
        # 主题到行业的粗匹配(AI 半导体 / 半导体 / 集成电路 / 消费电子)
        theme_keywords = {
            "AI 半导体": ["半导体", "集成电路", "消费电子", "光学光电子", "元件"],
            "半导体": ["半导体", "集成电路"],
            "资源": ["钢铁", "有色金属", "采掘", "化工"],
            "银行": ["银行"],
            "CPO": ["通信", "光学光电子", "半导体"],
        }
        keywords = theme_keywords.get(theme, [theme])
        matched = [
            ind for ind in industries
            if any(kw in ind.get("name", "") for kw in keywords)
        ][:5]

        candidates: list[dict] = []
        for ind in matched:
            try:
                # Lixinger industry list 用 stockCode 字段 (不是 code)
                constituents = lixinger.get_industry_constituents(ind["stockCode"])[:20]
                candidates.extend(constituents)
            except Exception as exc:
                print(f"  ⚠ industry {ind.get('name')} constituents failed: {exc}")

        def _extract_name(stock_name_obj: Any) -> str:
            if isinstance(stock_name_obj, dict):
                return stock_name_obj.get("cmn_hans_cn") or stock_name_obj.get("en") or ""
            return str(stock_name_obj)

        snapshot = {
            "theme": theme,
            "market": market,
            "time_window": TIME_WINDOW,
            "candidates_hint": [
                {"code": c.get("stockCode") or c.get("stock_code") or c.get("code"),
                 "name": _extract_name(c.get("stockName") or c.get("name")),
                 "industry": ind.get("name")}
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
        print(f"  ⚠ Lixinger context build failed (will fall back to LLM only): {exc}")
        return json.dumps({
            "theme": theme,
            "market": market,
            "time_window": TIME_WINDOW,
            "note": f"Lixinger 上下文构建失败: {exc}. 请直接基于 web_search 结果构建公司宇宙。",
        }, ensure_ascii=False, indent=2)


def extract_submit_research_call(response: Any) -> dict[str, Any]:
    """从 chat completion 响应里提取 submit_research 工具调用结果。"""
    choices = response.choices or []
    if not choices:
        raise RuntimeError("LLM 返回空 choices")
    msg = choices[0].message
    tool_calls = getattr(msg, "tool_calls", None) or []
    for tc in tool_calls:
        fn = getattr(tc, "function", None)
        if not fn or fn.name != "submit_research":
            continue
        try:
            return json.loads(fn.arguments)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"submit_research arguments 非法 JSON: {exc}\n原始: {fn.arguments[:500]}"
            ) from exc
    # 没找到 submit_research 调用,可能是 LLM 直接输出了 markdown
    content = getattr(msg, "content", None) or ""
    raise RuntimeError(
        f"LLM 未调用 submit_research 工具。content 前 500 字符:\n{content[:500]}"
    )


def render_markdown(result: dict[str, Any], stats: dict[str, Any]) -> str:
    """把结构化结果渲染成人类可读 Markdown 报告。"""
    lines: list[str] = []
    lines.append(f"# {stats['theme']} - serenity 研究报告\n")
    lines.append(f"> Market: {stats['market']} | Time window: {stats['time_window']} | "
                 f"Model: {stats['model']} | 用时: {stats['elapsed_sec']:.0f}s | "
                 f"Token: in={stats['token_input']} out={stats['token_output']} | "
                 f"Search: {stats['search_count']}\n")

    lines.append("## 1. 系统变化\n")
    lines.append(result["system_change"] + "\n")

    lines.append("## 2. 价值链 8 层\n")
    lines.append("| # | 层级 | 描述 |")
    lines.append("|---|---|---|")
    for layer in result["value_chain"]:
        lines.append(f"| {layer['layer_index']} | {layer['name']} | {layer['description']} |")
    lines.append("")

    lines.append("## 3. 稀缺层排名\n")
    lines.append("| Rank | 层级 | 推理 | 扩产难度 |")
    lines.append("|---|---|---|---|")
    for sl in sorted(result["scarce_layers"], key=lambda x: x["rank"]):
        lines.append(f"| {sl['rank']} | L{sl['layer_index']} | {sl['reason']} | {sl['difficulty']} |")
    lines.append("")

    lines.append("## 4. 公司宇宙\n")
    lines.append(f"共 {len(result['company_universe'])} 家:\n")
    lines.append("| Code | Name | Classification | Layer | Note |")
    lines.append("|---|---|---|---|---|")
    for c in result["company_universe"]:
        layer = c.get("layer_index", "-")
        note = c.get("note", "")
        lines.append(f"| {c['stock_code']} | {c['name']} | {c['classification']} | {layer} | {note} |")
    lines.append("")

    lines.append("## 5. 证据链\n")
    lines.append(f"共 {len(result['evidence'])} 条:\n")
    by_grade: dict[str, list] = {"strong": [], "medium": [], "weak": [], "lead": []}
    for ev in result["evidence"]:
        by_grade.setdefault(ev["grade"], []).append(ev)
    for grade in ["strong", "medium", "weak", "lead"]:
        items = by_grade.get(grade, [])
        if not items:
            continue
        lines.append(f"### {grade.upper()} ({len(items)} 条)\n")
        for ev in items:
            stock = ev.get("stock_code", "-")
            lines.append(f"- **[{stock}] {ev['source_title']}** ({ev['source_type']})")
            lines.append(f"  - URL: {ev['source_url']}")
            lines.append(f"  - 摘要: {ev['summary']}")
        lines.append("")

    lines.append("## 6. Top 公司排名\n")
    lines.append("| Rank | Code | Name | 卡住的环节 | 产业链位置 | 排序原因 | 主要风险 |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in sorted(result["company_ranking"], key=lambda x: x["rank"]):
        lines.append(
            f"| {r['rank']} | {r['stock_code']} | {r['name']} | "
            f"{r['constrains_what']} | {r['chain_position']} | "
            f"{r['rank_reason']} | {r['main_risk']} |"
        )
    lines.append("")

    lines.append("## 7. 失败条件 (什么情况说明这个判断错了)\n")
    for i, fc in enumerate(result["failure_conditions"], 1):
        lines.append(f"{i}. {fc}")
    lines.append("")

    lines.append("## 8. 下一步验证\n")
    for i, ns in enumerate(result["next_steps"], 1):
        lines.append(f"{i}. {ns}")
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    if not ZHIPU_API_KEY:
        print("错误: ZHIPU_API_KEY 未配置。")
        print("  1. 访问 https://open.bigmodel.cn/usercenter/apikeys 获取 API key")
        print("  2. 加到 backend/.env:")
        print("     ZHIPU_API_KEY=<your-key>")
        print("     ZHIPU_MODEL=glm-4.7  # 或 glm-5.1 / glm-5.2")
        return 1

    print(f"开始 serenity spike:")
    print(f"  主题: {THEME}")
    print(f"  市场: {MARKET}")
    print(f"  时间窗: {TIME_WINDOW}")
    print(f"  Model: {ZHIPU_MODEL}")
    print(f"  max_tokens: {MAX_TOKENS} / max_searches: {MAX_SEARCHES} / timeout: {TIMEOUT_SEC}s")
    print()

    client = ZhipuAI(api_key=ZHIPU_API_KEY)

    print("Step 1/3: 从 Lixinger 拉行业成分股上下文...")
    user_context = build_user_context(THEME, MARKET)
    print(f"  ✓ 上下文长度: {len(user_context)} 字符")

    print(f"\nStep 2/3: 调用 GLM 跑 serenity 完整工作流 (timeout={TIMEOUT_SEC}s)...")
    started = time.time()
    try:
        response = client.chat.completions.create(
            model=ZHIPU_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_context},
            ],
            tools=[
                {
                    "type": "web_search",
                    "web_search": {
                        "enable": True,
                        "search_result": False,  # 不回显搜索结果给 LLM,只让它消费
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "submit_research",
                        "description": "提交 serenity 研究结果 (必须调用,且只调用一次)",
                        "parameters": SERENITY_RESEARCH_JSON_SCHEMA,
                    },
                },
            ],
            tool_choice="auto",
            max_tokens=MAX_TOKENS,
            temperature=0.3,
            timeout=TIMEOUT_SEC,
        )
    except Exception as exc:
        elapsed = time.time() - started
        print(f"\n✗ GLM 调用失败 (用时 {elapsed:.0f}s): {exc}")
        return 2

    elapsed = time.time() - started
    print(f"  ✓ GLM 返回 (用时 {elapsed:.0f}s)")

    print("\nStep 3/3: 解析结构化结果 + 落盘...")
    result = extract_submit_research_call(response)

    usage = getattr(response, "usage", None)
    token_input = getattr(usage, "prompt_tokens", 0) if usage else 0
    token_output = getattr(usage, "completion_tokens", 0) if usage else 0
    # web_search 调用次数需要从 tool_calls 历史里数
    search_count = 0
    try:
        for choice in response.choices or []:
            msg = choice.message
            for tc in getattr(msg, "tool_calls", None) or []:
                fn = getattr(tc, "function", None)
                if fn and fn.name == "web_search":
                    search_count += 1
    except Exception:
        pass

    stats = {
        "theme": THEME,
        "market": MARKET,
        "time_window": TIME_WINDOW,
        "model": ZHIPU_MODEL,
        "elapsed_sec": elapsed,
        "token_input": token_input,
        "token_output": token_output,
        "search_count": search_count,
        "company_count": len(result.get("company_universe", [])),
        "evidence_count": len(result.get("evidence", [])),
        "ranking_count": len(result.get("company_ranking", [])),
    }

    # 落盘
    (OUTPUT_DIR / "serenity_demo.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2)
    )
    (OUTPUT_DIR / "serenity_demo.md").write_text(render_markdown(result, stats))
    stats_lines = [
        "=== serenity spike stats ===",
        f"theme: {THEME}",
        f"market: {MARKET}",
        f"model: {ZHIPU_MODEL}",
        f"elapsed_sec: {elapsed:.0f}",
        f"token_input: {token_input}",
        f"token_output: {token_output}",
        f"search_count: {search_count}",
        f"company_universe: {stats['company_count']} (target >= 20)",
        f"evidence: {stats['evidence_count']} (target >= 25)",
        f"company_ranking: {stats['ranking_count']} (target 3-7)",
        "",
        "=== schema validation ===",
    ]
    # 简单 schema 校验
    for field in ["system_change", "value_chain", "scarce_layers",
                  "company_universe", "evidence", "company_ranking",
                  "failure_conditions", "next_steps"]:
        present = field in result and len(result[field]) > 0 if isinstance(result.get(field), list) else field in result
        stats_lines.append(f"  {field}: {'✓' if present else '✗ MISSING'}")

    # 通过标准
    stats_lines.extend([
        "",
        "=== pass criteria ===",
        f"  company_universe >= 20: {'✓ PASS' if stats['company_count'] >= 20 else '✗ FAIL'}",
        f"  evidence >= 25: {'✓ PASS' if stats['evidence_count'] >= 25 else '✗ FAIL'}",
        f"  ranking in [3, 7]: {'✓ PASS' if 3 <= stats['ranking_count'] <= 7 else '✗ FAIL'}",
        f"  token_input < 80000: {'✓ PASS' if token_input < 80000 else '✗ FAIL'}",
        f"  elapsed < 300s: {'✓ PASS' if elapsed < 300 else '⚠ SLOW'}",
    ])
    (OUTPUT_DIR / "serenity_stats.txt").write_text("\n".join(stats_lines))

    print("\n" + "\n".join(stats_lines))
    print(f"\n输出文件:")
    print(f"  {OUTPUT_DIR / 'serenity_demo.json'}")
    print(f"  {OUTPUT_DIR / 'serenity_demo.md'}")
    print(f"  {OUTPUT_DIR / 'serenity_stats.txt'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
