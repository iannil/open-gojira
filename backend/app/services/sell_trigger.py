"""sell_trigger — 卖出信号 2/3/5 自动触发 (Phase 5, decision 2-A/9).

触发 2：估值 > 1.3x 历史中位 → TRIM 50% (估值止盈)
触发 3：仓位 > 15% → TRIM 回 10% (仓位再平衡)
触发 5：news_pulse/earnings_review 基本面恶化 → SELL 100% (通过接线)

信号 1 (thesis INVALIDATED → SELL 100%) 实现在 draft_service.py 的
create_thesis_breach_sell_draft() 中，被 thesis_tracker 调用。

用法:
    from app.services.sell_trigger import run_all_signals
    result = run_all_signals(db)
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.core.datetime_utils import now
from app.models.draft import Draft
from app.models.valuation import ValuationSnapshot
from app.services import draft_service, holding_service, position_service

logger = logging.getLogger(__name__)

# ── 阈值 ───────────────────────────────────────────────────────────────────

# 触发 2: PE 历史百分位 > 此值视为「估值 > 1.3x 中位」
VALUATION_PCT_THRESHOLD: float = 90.0
"""PE/PB 百分位 ≥90 → 估值远超历史中位，等价于 > 1.3x median。"""

TRIM_RATIO_OVERVAULED: float = 0.5
"""估值止盈: TRIM 50% 仓位。"""

# 触发 3: 单股仓位百分比超过此值触发 TRIM
MAX_POSITION_WEIGHT_PCT: float = 15.0
"""决策 3: 单股 >15% 触发 TRIM。"""

TRIM_TARGET_WEIGHT_PCT: float = 10.0
"""TRIM 目标: 回到 10%。"""

# 触发 5: news_pulse action 等于此值时视为基本面恶化
FUNDAMENTAL_DETERIORATION_ACTION: str = "thesis_review"
"""news_pulse action_recommendation == thesis_review → 触发 SELL。"""


# ── 信号 2：估值止盈 ──────────────────────────────────────────────────────


def _latest_valuation(
    db: Session, stock_code: str
) -> Optional[ValuationSnapshot]:
    """获取某只股票的最新估值快照。"""
    return (
        db.query(ValuationSnapshot)
        .filter(ValuationSnapshot.stock_code == stock_code)
        .order_by(ValuationSnapshot.date.desc())
        .first()
    )


def _is_overvalued(val: ValuationSnapshot) -> bool:
    """判断估值是否超过 1.3x 历史中位 (百分位 ≥90)。"""
    if val.pe_percentile_10y is not None and val.pe_percentile_10y >= VALUATION_PCT_THRESHOLD:
        return True
    if val.pb_percentile_10y is not None and val.pb_percentile_10y >= VALUATION_PCT_THRESHOLD:
        return True
    return False


def scan_valuation_overvalued(db: Session) -> list[dict]:
    """信号 2: 遍历持仓，找出估值超限的 → TRIM 50%。

    Returns:
        每个触发项的 dict 列表: {stock_code, reason, draft_id}
    """
    triggers: list[dict] = []
    codes = sorted(position_service.held_stock_codes(db))
    for code in codes:
        val = _latest_valuation(db, code)
        if val is None or not _is_overvalued(val):
            continue

        reason = (
            f"[触发 2 估值止盈] {code}: PE百分位={val.pe_percentile_10y}%, "
            f"PB百分位={val.pb_percentile_10y}% ≥ {VALUATION_PCT_THRESHOLD}% 阈值 → "
            f"TRIM {TRIM_RATIO_OVERVAULED*100:.0f}% 仓位 (决策 2-A)"
        )

        draft = draft_service.create_thesis_breach_sell_draft(
            db,
            stock_code=code,
            reason=reason,
            reduce_pct_of_position=TRIM_RATIO_OVERVAULED,
        )
        if draft:
            triggers.append({"stock_code": code, "reason": reason, "draft_id": draft.id})
            logger.info("sell_trigger[2]: %s → draft #%s (TRIM %.0f%%)", code, draft.id, TRIM_RATIO_OVERVAULED * 100)

    return triggers


# ── 信号 3：仓位超限 ──────────────────────────────────────────────────────


def scan_position_overweight(db: Session) -> list[dict]:
    """信号 3: 遍历持仓，找出仓位超过 MAX_POSITION_WEIGHT_PCT 的 → TRIM 回 10%。

    Returns:
        每个触发项的 dict 列表: {stock_code, weight_pct, target_pct, ratio, draft_id}
    """
    triggers: list[dict] = []
    summary = holding_service.get_portfolio_summary(db)
    holdings = summary.get("holdings") or []
    for h in holdings:
        code = h.get("stock_code")
        weight_pct = h.get("weight_pct") or 0.0
        if not code or weight_pct <= MAX_POSITION_WEIGHT_PCT:
            continue

        # 计算需要减仓的比例: (current - target) / current
        reduce_ratio = (weight_pct - TRIM_TARGET_WEIGHT_PCT) / weight_pct
        reduce_ratio = min(reduce_ratio, 1.0)  # 最多 100%

        reason = (
            f"[触发 3 仓位超限] {code}: 当前仓位 {weight_pct:.1f}% > "
            f"{MAX_POSITION_WEIGHT_PCT}% 阈值 → TRIM 回 {TRIM_TARGET_WEIGHT_PCT}% "
            f"(减仓 {reduce_ratio*100:.0f}% 当前仓位，决策 3)"
        )

        draft = draft_service.create_thesis_breach_sell_draft(
            db,
            stock_code=code,
            reason=reason,
            reduce_pct_of_position=reduce_ratio,
        )
        if draft:
            triggers.append({
                "stock_code": code,
                "weight_pct": round(weight_pct, 2),
                "target_pct": TRIM_TARGET_WEIGHT_PCT,
                "ratio": round(reduce_ratio, 3),
                "draft_id": draft.id,
            })
            logger.info(
                "sell_trigger[3]: %s weight=%.1f%% → draft #%s (reduce %.0f%%)",
                code, weight_pct, draft.id, reduce_ratio * 100,
            )

    return triggers


# ── 信号 5：news_pulse/earnings_review 基本面恶化 ─────────────────────────


def check_fundamental_deterioration(
    db: Session,
    stock_code: str,
    *,
    action_recommendation: str,
    pipeline_type: str,
    detail: str,
) -> Optional[dict]:
    """信号 5: 检查 Pipeline 输出是否指示基本面恶化，是则创建 SELL draft。

    Args:
        stock_code: 目标股票
        action_recommendation: news_pulse 的 action_recommendation 或
            earnings_review 的 thesis_impact
        pipeline_type: "news_pulse" | "earnings_review"
        detail: 基本面恶化的具体描述

    Returns:
        {stock_code, reason, draft_id} 或 None
    """
    # news_pulse: action_recommendation == thesis_review → 基本面恶化
    # earnings_review: thesis_impact == invalidates → 论文证伪
    is_deteriorated = False
    trigger_label = ""

    if pipeline_type == "news_pulse":
        if action_recommendation == FUNDAMENTAL_DETERIORATION_ACTION:
            is_deteriorated = True
            trigger_label = "news_pulse 基本面恶化"
    elif pipeline_type == "earnings_review":
        if action_recommendation == "invalidates":
            is_deteriorated = True
            trigger_label = "earnings_review 论文证伪"

    if not is_deteriorated:
        return None

    reason = f"[触发 5 {trigger_label}] {stock_code}: {detail} → SELL 100% (决策 5)"
    draft = draft_service.create_thesis_breach_sell_draft(
        db,
        stock_code=stock_code,
        reason=reason,
        reduce_pct_of_position=1.0,
    )
    if draft:
        logger.info("sell_trigger[5]: %s → draft #%s (SELL 100%%)", stock_code, draft.id)
        return {"stock_code": stock_code, "reason": reason, "draft_id": draft.id}
    return None


# ── 聚合入口 ──────────────────────────────────────────────────────────────


def run_all_signals(db: Session) -> dict:
    """运行所有卖出信号 (2, 3)，返回汇总。

    Note:
        信号 1 (thesis INVALIDATED) 由 thesis_tracker_pipeline 直接调用
        draft_service.create_thesis_breach_sell_draft()，不在这里运行。
        信号 5 由 news_pulse/earnings_review Pipeline 的调用者触发。

    Returns:
        {
            "valuation_overvalued": [...],
            "position_overweight": [...],
            "total_drafts": int,
        }
    """
    sig2 = scan_valuation_overvalued(db)
    sig3 = scan_position_overweight(db)
    total = len(sig2) + len(sig3)

    result = {
        "valuation_overvalued": sig2,
        "position_overweight": sig3,
        "total_drafts": total,
    }
    logger.info("sell_trigger: run_all_signals → %d drafts (sig2=%d, sig3=%d)", total, len(sig2), len(sig3))
    return result


# ── Pipeline 接线 ──────────────────────────────────────────────────────────
#
# 以下函数将 Pipeline 输出与卖出信号 5 接线:
#   news_pulse: action_recommendation == "thesis_review" → SELL
#   earnings_review: thesis_impact == "invalidates" → SELL
#
# 用法: 在调用 pipeline.run() 之后调用对应函数。


def run_news_pulse_with_sell_check(
    db: Session,
    stock_code: str,
    *,
    window_days: int = 7,
    auto_create_draft: bool = True,
    **kwargs,
) -> dict:
    """运行 news_pulse pipeline 并在检测到基本面恶化时自动创建 SELL draft。

    Args:
        db: 数据库会话
        stock_code: 目标股票
        window_days: 价格变动观察窗口 (天)
        auto_create_draft: 是否自动创建 Sell draft (默认 True)
        **kwargs: 传递给 news_pulse_pipeline.run() 的其他参数

    Returns:
        {"pipeline_result": NewsPulseResult, "sell_draft": dict|None}
    """
    from app.services.pipelines.llm import news_pulse_pipeline

    result = news_pulse_pipeline.run(
        stock_code,
        window_days=window_days,
        db_session=db,
        **kwargs,
    )

    sell_draft = None
    if auto_create_draft:
        sell_draft = check_fundamental_deterioration(
            db,
            stock_code=stock_code,
            action_recommendation=result.action,
            pipeline_type="news_pulse",
            detail=result.key_finding if hasattr(result, "key_finding") else result.markdown_report[:200],
        )

    return {"pipeline_result": result, "sell_draft": sell_draft}


def run_earnings_review_with_sell_check(
    db: Session,
    stock_code: str,
    *,
    auto_create_draft: bool = True,
    **kwargs,
) -> dict:
    """运行 earnings_review pipeline 并在检测到论文证伪时自动创建 SELL draft。

    Args:
        db: 数据库会话
        stock_code: 目标股票
        auto_create_draft: 是否自动创建 Sell draft (默认 True)
        **kwargs: 传递给 earnings_review_pipeline.run() 的其他参数

    Returns:
        {"pipeline_result": EarningsReviewResult, "sell_draft": dict|None}
    """
    from app.services.pipelines.llm import earnings_review_pipeline

    result = earnings_review_pipeline.run(
        stock_code,
        db_session=db,
        **kwargs,
    )

    sell_draft = None
    if auto_create_draft:
        sell_draft = check_fundamental_deterioration(
            db,
            stock_code=stock_code,
            action_recommendation=result.thesis_impact,
            pipeline_type="earnings_review",
            detail=(
                f"thesis_impact={result.thesis_impact}, "
                f"action={result.action_recommendation}"
            ),
        )

    return {"pipeline_result": result, "sell_draft": sell_draft}
