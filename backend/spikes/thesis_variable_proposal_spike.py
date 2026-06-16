"""Spike: thesis_variable_proposal_service with real GLM call on run 8 claims.

Phase 2 #9 阶段 B v2 spec — spike propose_for_run(run_id=8) before implementation.

Validates:
- LLM output schema parseable (含 breach_when)
- signal 文本 < 翻译成 breach_when=lt 正确率
- propose 数量 + source 分布
- 业务级 dedup (跨 run 同 signal)
- 误判率 (LLM 编阈值 vs 合理提议)

Output: backend/spikes/output/thesis_variable_proposal_<ts>.json
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure backend/ is on path when run from repo root or backend/
BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from sqlalchemy import select  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models.research_claim import ResearchClaim  # noqa: E402
from app.services.llm.zhipu_client import get_zhipu_client  # noqa: E402


# ── Source shortlist (v2 spec line ~146) ──────────────────────────────
SOURCE_SHORTLIST = [
    {"key": "financial:NIM", "desc": "净息差 (银行)", "example_signal": "净息差<1.3%"},
    {"key": "financial:NPL", "desc": "不良贷款率 (银行)", "example_signal": "不良率>2%"},
    {"key": "financial:revenue_growth", "desc": "营收同比增速", "example_signal": "营收增速<5%"},
    {"key": "financial:margin", "desc": "毛利率 (制造业)", "example_signal": "毛利率<30%"},
    {"key": "valuation:PE_percentile", "desc": "PE 10y 分位", "example_signal": "PE分位>90%"},
    {"key": "valuation:PB_percentile", "desc": "PB 10y 分位", "example_signal": "PB分位>90%"},
    {"key": "kline:price_drop_52w", "desc": "52 周跌幅", "example_signal": "52周跌幅>40%"},
]


SUBMIT_CLAIM_VARIABLES_SCHEMA = {
    "type": "object",
    "properties": {
        "proposals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim_id": {"type": "integer"},
                    "stock_code": {"type": "string"},
                    "variable_name": {"type": "string"},
                    "threshold_critical": {"type": "number"},
                    "breach_when": {"type": "string", "enum": ["lt", "gt"]},
                    "source": {"type": "string"},
                    "unit": {"type": "string"},
                    "window_periods": {"type": "integer"},
                    "rationale": {"type": "string"},
                },
                "required": [
                    "claim_id", "stock_code", "variable_name",
                    "threshold_critical", "breach_when", "source",
                ],
            },
        },
        "skipped_claim_ids": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "claim 无可监控的数据源,跳过",
        },
    },
    "required": ["proposals"],
}


SYSTEM_PROMPT = """你是 A 股投资论点监控系统助手。给定一批 research_claims (每条带 signal 文本),
你的任务是把 signal 翻译成可监控的 thesis variable 提议。

## 输出规则

1. 每条 claim × 每个 stock_code (claim.stock_codes 数组里的) 输出一条 proposal (若 signal 可量化)
2. 如果 signal 描述的是模糊事件 (e.g. "招标数量下滑"、"硬钱包发行量"),没有明确数字阈值,把 claim_id 放进 skipped_claim_ids
3. source 必须从下方 shortlist 选,不能编造
4. **breach_when 字段**: 字面对齐 signal 文本里的比较符
   - signal 写 "<X" 或 "低于X" 或 "跌破X" → breach_when="lt" (低于阈值时告警)
   - signal 写 ">X" 或 "高于X" 或 "突破X" → breach_when="gt" (高于阈值时告警)
   - 例子: "净息差<1.3%" → breach_when="lt", threshold_critical=1.3
   - 例子: "不良率突破2%" → breach_when="gt", threshold_critical=2.0
5. window_periods: signal 写 "持续两季" / "连续两个季度" → 2; 否则省略 (单点)
6. unit: "%" / "倍" / null

## source shortlist (强制从此列表选)

```
{shortlist}
```

## 重要约束

- next_step 类型的 claim 也可以提议 (用户想验证假设)
- failure_condition 类型是核心目标 (失败预警)
- 不要给同一 (claim_id, stock_code) 提议多条 (一个 signal = 一个 monitor variable)
- 跳过的 claim 必须放进 skipped_claim_ids,不要静默丢弃
""".format(
    shortlist=json.dumps(SOURCE_SHORTLIST, ensure_ascii=False, indent=2)
)


def build_user_prompt(claims: list[ResearchClaim]) -> str:
    """Build prompt with claim list — only essential fields."""
    payload = []
    for c in claims:
        try:
            codes = json.loads(c.stock_codes_json or "[]")
        except json.JSONDecodeError:
            codes = []
        payload.append({
            "claim_id": c.id,
            "type": c.type,
            "subject": c.subject,
            "signal": c.signal,
            "outcome": c.outcome[:120] if c.outcome else "",
            "stock_codes": codes,
        })

    return (
        "# 待监控的 research claims\n\n"
        "请把每条 claim 的 signal 翻译成 thesis variable proposal,或放进 skipped_claim_ids。\n\n"
        "```json\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + "\n```"
    )


def run_spike(run_id: int = 8) -> dict[str, Any]:
    db = SessionLocal()
    try:
        claims = list(
            db.execute(
                select(ResearchClaim).where(ResearchClaim.research_run_id == run_id)
            ).scalars().all()
        )
        if not claims:
            return {"error": f"no claims for run {run_id}"}

        print(f"[spike] run {run_id}: {len(claims)} claims")
        for c in claims[:5]:
            print(f"  #{c.id} {c.type} signal={c.signal!r}")

        client = get_zhipu_client()
        user_prompt = build_user_prompt(claims)

        print(f"\n[spike] calling GLM (model={client._model})...")
        response = client._client.chat.completions.create(
            model=client._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "submit_claim_variables",
                        "description": "提交 thesis variable 提议 (必须调用,且只调用一次)",
                        "parameters": SUBMIT_CLAIM_VARIABLES_SCHEMA,
                    },
                }
            ],
            tool_choice="auto",
            max_tokens=4000,
            temperature=0.2,
            timeout=180,
        )

        # Extract tool_call
        msg = response.choices[0].message
        tool_calls = getattr(msg, "tool_calls", None) or []
        result = None
        for tc in tool_calls:
            fn = getattr(tc, "function", None)
            if fn and fn.name == "submit_claim_variables":
                result = json.loads(fn.arguments)
                break

        if not result:
            return {
                "error": "LLM did not call submit_claim_variables",
                "content_head": (getattr(msg, "content", "") or "")[:500],
            }

        usage = getattr(response, "usage", None)
        usage_dict = {
            "token_input": getattr(usage, "prompt_tokens", 0) if usage else 0,
            "token_output": getattr(usage, "completion_tokens", 0) if usage else 0,
            "model": client._model,
        }

        # ── Analysis ───────────────────────────────────────────────────
        proposals = result.get("proposals", [])
        skipped = result.get("skipped_claim_ids", [])

        # source distribution
        source_dist: dict[str, int] = {}
        for p in proposals:
            source_dist[p["source"]] = source_dist.get(p["source"], 0) + 1

        # breach_when correctness vs signal text
        breach_analysis = []
        claim_by_id = {c.id: c for c in claims}
        for p in proposals:
            claim = claim_by_id.get(p["claim_id"])
            if not claim or not claim.signal:
                continue
            sig = claim.signal
            # crude heuristic
            has_lt = any(tok in sig for tok in ["<", "低于", "跌破", "下滑超", "下降超"])
            has_gt = any(tok in sig for tok in [">", "高于", "突破", "增长超", "上行超"])
            if has_lt and not has_gt:
                expected = "lt"
            elif has_gt and not has_lt:
                expected = "gt"
            else:
                expected = "ambiguous"
            actual = p.get("breach_when")
            breach_analysis.append({
                "claim_id": p["claim_id"],
                "signal": sig,
                "expected_breach_when": expected,
                "actual_breach_when": actual,
                "correct": expected == actual if expected != "ambiguous" else None,
                "threshold": p.get("threshold_critical"),
                "stock": p["stock_code"],
            })

        correct_count = sum(1 for b in breach_analysis if b["correct"] is True)
        checked = sum(1 for b in breach_analysis if b["correct"] is not None)
        accuracy = correct_count / checked if checked else 0

        # per-claim coverage
        proposed_claim_ids = {p["claim_id"] for p in proposals}
        all_claim_ids = {c.id for c in claims}
        skipped_set = set(skipped)
        no_action = all_claim_ids - proposed_claim_ids - skipped_set

        return {
            "run_id": run_id,
            "total_claims": len(claims),
            "proposals_count": len(proposals),
            "skipped_count": len(skipped),
            "no_action_count": len(no_action),
            "no_action_claim_ids": sorted(no_action),
            "source_distribution": source_dist,
            "breach_when_accuracy": {
                "correct": correct_count,
                "checked": checked,
                "accuracy": round(accuracy, 3),
                "details": breach_analysis,
            },
            "usage": usage_dict,
            "proposals": proposals,
            "skipped_claim_ids": skipped,
        }
    finally:
        db.close()


def main() -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    out_dir = BACKEND / "spikes" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"thesis_variable_proposal_{ts}.json"

    result = run_spike(run_id=8)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))

    print(f"\n[spike] output → {out_path}")
    print(f"\n=== Summary ===")
    if "error" in result:
        print(f"ERROR: {result['error']}")
        if 'content_head' in result:
            print(f"content head:\n{result['content_head']}")
        return

    print(f"total_claims:       {result['total_claims']}")
    print(f"proposals_count:    {result['proposals_count']}")
    print(f"skipped_count:      {result['skipped_count']}")
    print(f"no_action_count:    {result['no_action_count']}")
    print(f"source_distribution:{result['source_distribution']}")
    ba = result["breach_when_accuracy"]
    print(f"breach_when accuracy: {ba['correct']}/{ba['checked']} = {ba['accuracy']}")
    print(f"tokens:             in={result['usage']['token_input']} out={result['usage']['token_output']}")
    print(f"\n=== Proposals (first 10) ===")
    for p in result["proposals"][:10]:
        print(f"  claim #{p['claim_id']} {p['stock_code']} {p['variable_name']!r}"
              f" {p.get('breach_when')} threshold={p.get('threshold_critical')}"
              f" source={p['source']} window={p.get('window_periods')}")
    print(f"\n=== Skipped ===")
    print(f"  {result['skipped_claim_ids']}")
    print(f"\n=== Breach analysis ===")
    for b in ba["details"]:
        mark = "✓" if b["correct"] else "✗" if b["correct"] is False else "?"
        print(f"  {mark} claim #{b['claim_id']} sig={b['signal']!r}"
              f" expected={b['expected_breach_when']} actual={b['actual_breach_when']}"
              f" thr={b['threshold']}")


if __name__ == "__main__":
    main()
