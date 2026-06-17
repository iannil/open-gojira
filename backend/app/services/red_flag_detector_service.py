"""Red flag detector — invest1 §三 + invest2 §10 财报避坑。

实现 7 个机械红旗:
  1. goodwill_to_equity_gt_50: 商誉/净资产 > 50% (商誉雷)
  2. ocf_to_ni_lt_half_2y: OCF/NI < 0.5 持续 2 年 (利润虚高)
  3. low_dividend_sustainability: 分红可持续性 < 30
  4. ar_growth_gt_revenue: 应收账款增速 >> 营收增速 (伪造销售) [Batch 3 激活]
  5. inventory_turnover_drop: 存货周转率同比下降 > 30% (积压) [Batch 3 激活]
  6. non_recurring_dominant: 非经常损益/净利润 > 50% (主业虚弱) [Lixinger 不提供, 死代码]
  7. non_standard_audit_opinion: 非标准审计意见 [Batch 3 新增]

graceful degradation: 任何字段缺失 → 该红旗不触发, 不报错。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.financial import FinancialStatement

logger = logging.getLogger(__name__)

RedFlagKind = Literal[
    "goodwill_to_equity_gt_50",
    "ocf_to_ni_lt_half_2y",
    "low_dividend_sustainability",
    "ar_growth_gt_revenue",
    "inventory_turnover_drop",
    "non_recurring_dominant",
    "non_standard_audit_opinion",
]


@dataclass(frozen=True)
class RedFlag:
    kind: RedFlagKind
    detail: str


@dataclass(frozen=True)
class RedFlagReport:
    stock_code: str
    flags: list[RedFlag] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.flags)

    @property
    def kinds(self) -> list[str]:
        return [f.kind for f in self.flags]

    def to_dict(self) -> dict:
        return {
            "stock_code": self.stock_code,
            "count": self.count,
            "kinds": self.kinds,
            "details": [f.detail for f in self.flags],
        }


# 阈值常量 (invest1/2 文档语义化命名)
_GOODWILL_EQUITY_THRESHOLD = 0.50  # invest2 §10 商誉/净资产超 50% = 商誉雷
_OCF_NI_LOW = 0.50                  # invest1 §三 OCF<NI 一半 = 利润虚高
_LOW_DIV_SUST = 30                  # dividend_sustainability_service 已有评分体系
_AR_REVENUE_GAP = 2.0              # 应收增速超营收 2x = 伪造销售嫌疑
_INV_TURNOVER_DROP = 0.30           # 存货周转率同比下降 30%
_NON_RECURRING_DOMINANT = 0.50      # 非经常损益占净利润 > 50%


def _check_goodwill_to_equity(stmts: list[FinancialStatement]) -> RedFlag | None:
    """商誉/净资产 > 50% (最新年报)."""
    if not stmts:
        return None
    latest = stmts[0]
    if not latest.goodwill or not latest.shareholders_equity:
        return None
    if latest.shareholders_equity <= 0:
        return None
    ratio = latest.goodwill / latest.shareholders_equity
    if ratio > _GOODWILL_EQUITY_THRESHOLD:
        return RedFlag(
            kind="goodwill_to_equity_gt_50",
            detail=f"商誉/净资产 = {ratio*100:.1f}% > {_GOODWILL_EQUITY_THRESHOLD*100:.0f}% (商誉雷)",
        )
    return None


def _check_ocf_to_ni_low(stmts: list[FinancialStatement]) -> RedFlag | None:
    """OCF/NI < 0.5 持续 2 年 (利润虚高)."""
    if len(stmts) < 2:
        return None
    for s in stmts[:2]:
        if not s.net_profit or s.net_profit <= 0:
            return None
        if not s.operating_cash_flow:
            return None
        ratio = s.operating_cash_flow / s.net_profit
        if ratio >= _OCF_NI_LOW:
            return None
    return RedFlag(
        kind="ocf_to_ni_lt_half_2y",
        detail=f"近 2 年 OCF/NI 均 < {_OCF_NI_LOW*100:.0f}% (利润虚高嫌疑)",
    )


def _check_ar_growth_gt_revenue(stmts: list[FinancialStatement]) -> RedFlag | None:
    """应收账款增速 >> 营收增速 (伪造销售).

    需要至少 2 期数据 (本期 + 上期). 应收账款当前 fields 已有, 但增速需计算。
    简化: 若 latest.accounts_receivable / latest.revenue > 0.5 (应收占营收 > 50%)
    且营收同比下行, 触发红旗。
    """
    if len(stmts) < 2:
        return None
    latest, prev = stmts[0], stmts[1]
    if not (latest.accounts_receivable and latest.revenue and prev.accounts_receivable and prev.revenue):
        return None
    if prev.accounts_receivable <= 0 or prev.revenue <= 0:
        return None
    ar_growth = (latest.accounts_receivable - prev.accounts_receivable) / prev.accounts_receivable
    rev_growth = (latest.revenue - prev.revenue) / prev.revenue
    if ar_growth > rev_growth * _AR_REVENUE_GAP and ar_growth > 0.20:
        return RedFlag(
            kind="ar_growth_gt_revenue",
            detail=(
                f"应收账款增速 {ar_growth*100:.1f}% >> 营收增速 {rev_growth*100:.1f}% "
                f"(应收增速 > 营收×{_AR_REVENUE_GAP}x, 伪造销售嫌疑)"
            ),
        )
    return None


def _check_inventory_turnover_drop(stmts: list[FinancialStatement]) -> RedFlag | None:
    """存货周转率同比下降 > 30% (积压)."""
    if len(stmts) < 2:
        return None
    latest, prev = stmts[0], stmts[1]
    if not (latest.inventory_turnover_ratio and prev.inventory_turnover_ratio):
        return None
    if prev.inventory_turnover_ratio <= 0:
        return None
    drop = (prev.inventory_turnover_ratio - latest.inventory_turnover_ratio) / prev.inventory_turnover_ratio
    if drop > _INV_TURNOVER_DROP:
        return RedFlag(
            kind="inventory_turnover_drop",
            detail=(
                f"存货周转率 {latest.inventory_turnover_ratio:.2f} vs 上期 {prev.inventory_turnover_ratio:.2f} "
                f"(下降 {drop*100:.1f}%, 存货积压嫌疑)"
            ),
        )
    return None


def _check_non_recurring_dominant(stmts: list[FinancialStatement]) -> RedFlag | None:
    """非经常损益/净利润 > 50% (主业虚弱).

    简化: 若 non_recurring_profit_ratio > 50% (扣非净利率低于净利率 50% 以上),
    说明主业贡献 < 50%, 主业虚弱。

    Batch 3 (2026-06-17): Lixinger 不提供 ps.np_wd_s_r.t (spike 验证), 此检测器
    始终返回 None. 保留代码作为未来数据源支持时的设计意图。
    """
    if not stmts:
        return None
    latest = stmts[0]
    if not (latest.non_recurring_profit_ratio and latest.net_margin):
        return None
    # non_recurring_profit_ratio 是扣非净利率, 若远低于 net_margin 表示非经常损益占比大
    if latest.net_margin > 0:
        non_recurring_share = 1 - (latest.non_recurring_profit_ratio / latest.net_margin)
        if non_recurring_share > _NON_RECURRING_DOMINANT:
            return RedFlag(
                kind="non_recurring_dominant",
                detail=(
                    f"扣非净利率 {latest.non_recurring_profit_ratio*100:.1f}% vs 净利率 {latest.net_margin*100:.1f}% "
                    f"(非经常损益占比 {non_recurring_share*100:.1f}% > {_NON_RECURRING_DOMINANT*100:.0f}%)"
                ),
            )
    return None


# Lixinger auditOpinionType 已知值 (spike 2026-06-17):
#   unqualified_opinion (标准无保留) — 唯一"干净"值, 其他都视为红旗
_STANDARD_AUDIT_OPINIONS = {"unqualified_opinion", "standard_unqualified"}


def _check_non_standard_audit_opinion(stmts: list[FinancialStatement]) -> RedFlag | None:
    """非标准审计意见 (qualified / adverse / disclaimer / unqualified_with_emphasis).

    invest2 §10 "避开会计游戏": 非标准审计 = 财报可信度疑问.
    Batch 3 (2026-06-17) 新增, 字段映射来自 Lixinger top-level auditOpinionType.
    """
    if not stmts:
        return None
    latest = stmts[0]
    opinion = latest.audit_opinion
    if not opinion:
        return None
    if opinion not in _STANDARD_AUDIT_OPINIONS:
        return RedFlag(
            kind="non_standard_audit_opinion",
            detail=f"审计意见 = {opinion} (非标准无保留, 财报可信度疑问)",
        )
    return None


_CHECKS_FINANCIAL = [
    _check_goodwill_to_equity,
    _check_ocf_to_ni_low,
    _check_ar_growth_gt_revenue,
    _check_inventory_turnover_drop,
    _check_non_recurring_dominant,
    _check_non_standard_audit_opinion,
]


def _fetch_annual_stmts(db: Session, stock_code: str, limit: int = 4) -> list[FinancialStatement]:
    """Fetch last N annual reports sorted by date desc."""
    return list(
        db.execute(
            select(FinancialStatement)
            .where(
                FinancialStatement.stock_code == stock_code,
                FinancialStatement.report_type == "annual",
            )
            .order_by(FinancialStatement.report_date.desc())
            .limit(limit)
        ).scalars().all()
    )


def detect_financial_red_flags(db: Session, stock_code: str) -> RedFlagReport:
    """Run all financial-statement-based red flag checks.

    Args:
        db: SQLAlchemy session.
        stock_code: Stock code.

    Returns:
        RedFlagReport with count and kinds. Empty if no data.
    """
    stmts = _fetch_annual_stmts(db, stock_code)
    report = RedFlagReport(stock_code=stock_code)
    if not stmts:
        return report
    for check in _CHECKS_FINANCIAL:
        try:
            flag = check(stmts)
            if flag:
                report.flags.append(flag)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "red_flag check %s failed for %s: %s",
                check.__name__, stock_code, exc,
            )
    return report


def detect_with_dividend_sustainability(
    db: Session, stock_code: str, div_sust_score: float | None,
) -> RedFlagReport:
    """Combine financial red flags with dividend sustainability score.

    Args:
        db: SQLAlchemy session.
        stock_code: Stock code.
        div_sust_score: dividend_sustainability_service score (0-100), None if unavailable.

    Returns:
        RedFlagReport including dividend sustainability flag if score < 30.
    """
    report = detect_financial_red_flags(db, stock_code)
    if div_sust_score is not None and div_sust_score < _LOW_DIV_SUST:
        report.flags.append(RedFlag(
            kind="low_dividend_sustainability",
            detail=f"分红可持续性评分 {div_sust_score:.0f} < {_LOW_DIV_SUST} (invest2 §10)",
        ))
    return report
