"""Thesis variable proposal service (Phase 2 #9 阶段 B v2, 2026-06-16).

Triggered by EventBus ResearchRunCompleted. For each completed serenity run,
loads its research_claims and asks GLM to translate each claim.signal into
a monitorable thesis variable proposal.

Output rows in research_claim_variables (status='proposed') ready for user
review via /api/research/claim-variables endpoints.

v2 decisions applied:
- Q4'-C: do NOT copy to Stock.thesis_variables_json on approve.
- Q-new breach_when: "lt" | "gt" literal aligned with signal text comparator.
- Q-new dedup: business-level (stock, variable_name, source) + DB UniqueConstraint.
- Q-new audit: success / partial / failure all written to audit_log.
- Q3-A: LLM forced to pick source from shortlist; un-monitorable claims skipped.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.events import bus, ClaimVariablesProposed
from app.models.research_claim import ResearchClaim
from app.models.research_claim_variable import ResearchClaimVariable
from app.services.llm.zhipu_client import ZhipuClientError, get_zhipu_client

logger = logging.getLogger(__name__)


# ── Source shortlist (spec line ~146) ──────────────────────────────────
# Keep in sync with thesis_monitor_service.SOURCE_DISPATCH keys.

SOURCE_SHORTLIST = [
    {"key": "financial:NIM", "desc": "净息差 (银行)", "example_signal": "净息差<1.3%"},
    {"key": "financial:NPL", "desc": "不良贷款率 (银行)", "example_signal": "不良率>2%"},
    {"key": "financial:revenue_growth", "desc": "营收同比增速", "example_signal": "营收增速<5%"},
    {"key": "financial:margin", "desc": "毛利率 (制造业)", "example_signal": "毛利率<30%"},
    {"key": "valuation:PE_percentile", "desc": "PE 10y 分位", "example_signal": "PE分位>90%"},
    {"key": "valuation:PB_percentile", "desc": "PB 10y 分位", "example_signal": "PB分位>90%"},
    {"key": "kline:price_drop_52w", "desc": "52 周跌幅", "example_signal": "52周跌幅>40%"},
]

ALLOWED_SOURCES = {s["key"] for s in SOURCE_SHORTLIST}


SUBMIT_CLAIM_VARIABLES_SCHEMA: dict[str, Any] = {
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


class ProposeResult(BaseModel):
    """Summary of one propose_for_run call."""
    run_id: int
    total_claims: int
    proposed_count: int = 0
    skipped_count: int = 0  # LLM-tagged skipped
    deduped_count: int = 0  # already-proposed/active, business-level skip
    failed_count: int = 0   # schema validation failures
    failed_claim_ids: list[int] = []
    token_input: int = 0
    token_output: int = 0


# ── Core entry ─────────────────────────────────────────────────────────


def propose_for_run(db: Session, run_id: int) -> ProposeResult:
    """Generate thesis variable proposals for all claims of a serenity run.

    Workflow:
      1. Load research_claims for run_id
      2. Build prompt + call GLM via zhipu_client
      3. For each proposal: validate source, dedup-check, persist as 'proposed'
      4. Emit ClaimVariablesProposed event

    Returns ProposeResult summary. Caller is responsible for audit_log.

    Raises ZhipuClientError if LLM call fails (caller's responsibility to
    audit 'failed' state).
    """
    claims = list(
        db.execute(
            select(ResearchClaim).where(ResearchClaim.research_run_id == run_id)
        ).scalars().all()
    )

    result = ProposeResult(run_id=run_id, total_claims=len(claims))

    if not claims:
        logger.info("propose_for_run run_id=%s: no claims, skipping", run_id)
        bus.emit(ClaimVariablesProposed(
            run_id=run_id, proposed_count=0, skipped_count=0,
        ))
        return result

    client = get_zhipu_client()
    user_prompt = _build_user_prompt(claims)

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

    usage = getattr(response, "usage", None)
    result.token_input = getattr(usage, "prompt_tokens", 0) if usage else 0
    result.token_output = getattr(usage, "completion_tokens", 0) if usage else 0

    raw = _extract_tool_call(response)

    proposals_raw = raw.get("proposals", []) if raw else []
    skipped_ids = raw.get("skipped_claim_ids", []) if raw else []

    claim_ids = {c.id for c in claims}
    valid_skipped = [cid for cid in skipped_ids if cid in claim_ids]
    result.skipped_count = len(valid_skipped)

    proposed_claim_ids: set[int] = set()
    failed_claim_ids: list[int] = []

    for p in proposals_raw:
        claim_id = p.get("claim_id")
        if claim_id not in claim_ids:
            logger.warning("propose_for_run: claim_id=%s not in run %s, skipping",
                           claim_id, run_id)
            continue

        source = p.get("source")
        if source not in ALLOWED_SOURCES:
            logger.warning(
                "propose_for_run: claim_id=%s invalid source=%r (not in shortlist), skipping",
                claim_id, source,
            )
            if claim_id not in failed_claim_ids:
                failed_claim_ids.append(claim_id)
            continue

        try:
            inserted = _persist_proposal(db, p)
        except Exception:
            logger.exception(
                "propose_for_run: failed to persist proposal claim_id=%s stock=%s",
                claim_id, p.get("stock_code"),
            )
            if claim_id not in failed_claim_ids:
                failed_claim_ids.append(claim_id)
            continue

        if inserted:
            result.proposed_count += 1
            proposed_claim_ids.add(claim_id)
        else:
            result.deduped_count += 1
            # Still counts as "covered" — don't add to failed
            proposed_claim_ids.add(claim_id)

    result.failed_count = len(failed_claim_ids)
    result.failed_claim_ids = failed_claim_ids

    db.commit()

    bus.emit(ClaimVariablesProposed(
        run_id=run_id,
        proposed_count=result.proposed_count,
        skipped_count=result.skipped_count,
        failed_count=result.failed_count,
    ))

    logger.info(
        "propose_for_run run_id=%s: total=%s proposed=%s skipped=%s deduped=%s failed=%s tokens=%s/%s",
        run_id, result.total_claims, result.proposed_count,
        result.skipped_count, result.deduped_count, result.failed_count,
        result.token_input, result.token_output,
    )
    return result


# ── Helpers ────────────────────────────────────────────────────────────


def _build_user_prompt(claims: list[ResearchClaim]) -> str:
    payload = []
    for c in claims:
        try:
            codes = json.loads(c.stock_codes_json or "[]")
        except (json.JSONDecodeError, TypeError):
            codes = []
        payload.append({
            "claim_id": c.id,
            "type": c.type,
            "subject": c.subject,
            "signal": c.signal,
            "outcome": (c.outcome or "")[:120],
            "stock_codes": codes,
        })

    return (
        "# 待监控的 research claims\n\n"
        "请把每条 claim 的 signal 翻译成 thesis variable proposal,"
        "或放进 skipped_claim_ids。\n\n"
        "```json\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + "\n```"
    )


def _extract_tool_call(response: Any) -> dict[str, Any] | None:
    """Pull submit_claim_variables tool_call arguments."""
    choices = getattr(response, "choices", None) or []
    if not choices:
        return None
    msg = choices[0].message
    tool_calls = getattr(msg, "tool_calls", None) or []
    for tc in tool_calls:
        fn = getattr(tc, "function", None)
        if not fn or fn.name != "submit_claim_variables":
            continue
        try:
            return json.loads(fn.arguments)
        except json.JSONDecodeError as exc:
            logger.warning("submit_claim_variables invalid JSON: %s", exc)
            return None
    logger.warning("LLM did not call submit_claim_variables; content head: %s",
                   (getattr(msg, "content", "") or "")[:300])
    return None


def _persist_proposal(db: Session, p: dict[str, Any]) -> bool:
    """Insert one proposal row, applying business-level dedup.

    Returns True if a new row was inserted, False if dedup-skipped.
    """
    stock_code = p.get("stock_code")
    variable_name = p.get("variable_name")
    source = p.get("source")

    if not stock_code or not variable_name or not source:
        raise ValueError(f"missing required field in proposal: {p}")

    # Business-level dedup: skip if same (stock, var, source) already
    # proposed or active. Rejected rows don't block (user changed mind).
    existing = db.execute(
        select(ResearchClaimVariable).where(
            ResearchClaimVariable.stock_code == stock_code,
            ResearchClaimVariable.variable_name == variable_name,
            ResearchClaimVariable.source == source,
            ResearchClaimVariable.status.in_(["proposed", "active"]),
        ).limit(1)
    ).first()
    if existing:
        return False

    db.add(ResearchClaimVariable(
        research_claim_id=p["claim_id"],
        stock_code=stock_code,
        variable_name=variable_name,
        threshold_critical=float(p["threshold_critical"]),
        breach_when=p["breach_when"],  # validated upstream (schema enum)
        unit=p.get("unit"),
        source=source,
        window_periods=p.get("window_periods"),
        status="proposed",
    ))
    return True
