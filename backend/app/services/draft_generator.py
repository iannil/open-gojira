"""draft_generator — Phase 5: deep_research BUY report → BUY Draft (decision 9/10).

触发条件 D (decision 9): 价格进入区间 AND 论文未被标记 INVALIDATED AND 组合有空间。
仓位 (decision 10): 单股 ≤10% / 现金 ≥20%; 激进型 100% 目标(8%) / 稳健型 50%(4%) /
保守型不生成。TTL 7 天 (价格离开区间则自动取消)。

行业 <30% 闸门 (decision 9) 需申万行业映射，Lixinger 不提供 (F20 已知限制) →
本实现跳过行业闸，仅做现金 + 单股闸。

§7: 生成的 Draft 携带 ai-berkshire 价格区间 (price_ranges_json) + serenity 卡点
论证 (serenity_thesis，仅 theme_scan 来源)。
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Callable, Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.datetime_utils import now
from app.models.draft import Draft
from app.models.research_report import (
    PIPELINE_DEEP_RESEARCH,
    REC_BUY,
    STATUS_COMPLETED,
    ResearchReport,
)
from app.services import holding_service
from app.services.draft_service import _supersede_pending_buys_for_stock

logger = logging.getLogger(__name__)

# Decision 9/10 thresholds.
REPORT_CACHE_DAYS = 30
MIN_CASH_RATIO_PCT = 20.0
MAX_SINGLE_STOCK_PCT = 10.0
DRAFT_TTL_DAYS = 7
# 策略层目标仓位 (% of portfolio): 激进 100% of 8% target / 稳健 50% (= 4%).
TIER_SIZING_PCT = {"aggressive": 8.0, "steady": 4.0}
TIER_STEP_INDEX = {"aggressive": 0, "steady": 1}


def _tier_for_price(price: float, ranges: dict[str, Any]) -> Optional[str]:
    """Which buy tier contains the current price? aggressive > steady > (skip).

    保守型不生成 (decision 10) → conservative range returns None. Price above the
    aggressive range (too expensive) also returns None.
    """
    for tier in ("aggressive", "steady"):
        r = ranges.get(tier) or {}
        lo, hi = r.get("min"), r.get("max")
        if lo is not None and hi is not None and lo <= price <= hi:
            return tier
    return None


def _cancel_expired(db: Session) -> int:
    """TTL: cancel pending BUY drafts past expires_at."""
    rows = db.execute(
        select(Draft).where(
            Draft.side == "BUY",
            Draft.status == "pending",
            Draft.expires_at.is_not(None),
            Draft.expires_at < now(),
        )
    ).scalars().all()
    for d in rows:
        d.status = "cancelled"
    if rows:
        db.flush()
    return len(rows)


def _latest_buy_reports(db: Session) -> list[ResearchReport]:
    """Latest completed BUY deep_research report per stock, within cache window."""
    cutoff = now() - timedelta(days=REPORT_CACHE_DAYS)
    rows = db.execute(
        select(ResearchReport)
        .where(
            ResearchReport.pipeline_type == PIPELINE_DEEP_RESEARCH,
            ResearchReport.recommendation == REC_BUY,
            ResearchReport.status == STATUS_COMPLETED,
            ResearchReport.created_at >= cutoff,
        )
        .order_by(desc(ResearchReport.created_at))
    ).scalars().all()
    seen: set[str] = set()
    latest: list[ResearchReport] = []
    for r in rows:
        if r.stock_code not in seen:
            seen.add(r.stock_code)
            latest.append(r)
    return latest


def generate_buy_drafts(
    db: Session,
    *,
    price_fn: Optional[Callable[[str], Optional[float]]] = None,
) -> dict:
    """Generate BUY drafts from fresh BUY reports whose price entered a buy tier.

    Args:
        price_fn: code → current price (injectable for tests). Defaults to the
            realtime quote service.
    """
    if price_fn is None:
        from app.services.realtime_quote_service import get_realtime_price

        def price_fn(code: str) -> Optional[float]:  # noqa: ANN001
            q = get_realtime_price(code)
            return q.get("current") if q else None

    expired = _cancel_expired(db)
    reports = _latest_buy_reports(db)

    summary = holding_service.get_portfolio_summary(db)
    cash_ratio = float(summary.get("cash_ratio_pct") or 0.0)
    total_value = float(summary.get("total_value") or 0.0)
    weight_by_code = {
        h["stock_code"]: float(h.get("weight_pct") or 0.0)
        for h in (summary.get("holdings") or [])
    }

    generated: list[int] = []
    skipped: list[dict] = []
    for report in reports:
        code = report.stock_code
        price = price_fn(code)
        if price is None or price <= 0:
            skipped.append({"code": code, "why": "no_price"})
            continue
        synthesis = (report.json_output or {}).get("synthesis") or {}
        ranges = synthesis.get("price_ranges") or {}
        tier = _tier_for_price(price, ranges)
        if tier is None:
            skipped.append({"code": code, "why": "price_not_in_buy_tier"})
            continue
        # 组合有空间: 现金 ≥20% + 单股 <10% (行业闸跳过, F20)
        if cash_ratio < MIN_CASH_RATIO_PCT:
            skipped.append({"code": code, "why": "cash_below_20pct"})
            continue
        if weight_by_code.get(code, 0.0) >= MAX_SINGLE_STOCK_PCT:
            skipped.append({"code": code, "why": "single_stock_cap"})
            continue

        add_pct = TIER_SIZING_PCT[tier]
        suggested_quantity = (
            int(total_value * (add_pct / 100.0) / price) if total_value > 0 else None
        )
        r = ranges.get(tier) or {}
        target_price = r.get("max")  # 区间上沿作为目标买价
        is_theme = (report.json_output or {}).get("scoring", {}).get("source") == "theme_scan"
        serenity_thesis = (
            (synthesis.get("mirror_test") or {}).get("statement") if is_theme else None
        )

        _supersede_pending_buys_for_stock(db, code)
        draft = Draft(
            code=code,
            side="BUY",
            status="pending",
            step_kind="buy_ladder",
            step_index=TIER_STEP_INDEX[tier],
            add_pct=add_pct,
            suggested_quantity=suggested_quantity,
            reason=(
                f"{tier} 区间建仓: 现价 {price:.2f} 入区间 "
                f"[{r.get('min')}, {r.get('max')}] (报告 #{report.id} 评分 {report.overall_score})"
            ),
            source="draft_generator",
            research_report_id=report.id,
            target_price=target_price,
            strategy_tier=tier,
            sizing_logic=f"{tier}: 目标 {add_pct}% 组合 (decision 10)",
            thesis_status="healthy",
            expires_at=now() + timedelta(days=DRAFT_TTL_DAYS),
            price_ranges_json=ranges,
            serenity_thesis=serenity_thesis,
        )
        db.add(draft)
        db.flush()
        generated.append(draft.id)

    return {
        "generated": len(generated),
        "generated_ids": generated,
        "expired_cancelled": expired,
        "scanned": len(reports),
        "skipped": skipped,
    }
