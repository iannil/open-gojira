"""Bank blind-box analyzer — 银行股"盲盒可视化"分析.

Implements invest3 "银行盲盒可视化理论":
  - 股息率（一票否决）
  - 地域评分（人口流入/经济强）
  - 长周期 OCF/NI 匹配度
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.stock import Stock
from app.models.valuation import ValuationSnapshot

logger = logging.getLogger(__name__)

# Banks need at least 4% DYR to be considered
MIN_BANK_DYR = 0.04


@dataclass(frozen=True)
class BankBlindBox:
    code: str
    name: str
    dividend_yield: float | None
    hq_region: str | None
    region_score: float | None
    ocf_ni_verdict: str
    blind_box_verdict: str  # "可见" | "模糊" | "不可见"
    details: list[str]

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "name": self.name,
            "dividend_yield": self.dividend_yield,
            "hq_region": self.hq_region,
            "region_score": self.region_score,
            "ocf_ni_verdict": self.ocf_ni_verdict,
            "blind_box_verdict": self.blind_box_verdict,
            "details": self.details,
        }


def _latest_dyr(db: Session, code: str) -> float | None:
    row = db.execute(
        select(ValuationSnapshot.dividend_yield)
        .where(ValuationSnapshot.stock_code == code)
        .order_by(ValuationSnapshot.date.desc())
        .limit(1)
    ).scalar_one_or_none()
    return float(row) if row else None


def analyze(db: Session, code: str) -> BankBlindBox | None:
    """Run blind-box analysis on a bank stock."""
    stock = db.get(Stock, code)
    if not stock:
        return None

    details: list[str] = []
    score = 0

    # 1. Dividend yield (pass/fail)
    dyr = _latest_dyr(db, code)
    if dyr is not None and dyr >= MIN_BANK_DYR:
        score += 1
        details.append(f"股息率 {dyr:.2%} >= {MIN_BANK_DYR:.0%} ✓")
    elif dyr is not None:
        details.append(f"股息率 {dyr:.2%} < {MIN_BANK_DYR:.0%} ✗ (一票否决)")
    else:
        details.append("股息率数据缺失")

    # 2. Region score (manual annotation via hq_region)
    hq_region = stock.hq_region
    region_score = None
    if hq_region:
        # Pre-defined region scores (could be moved to a table)
        tier1 = {"北京", "上海", "深圳", "广东", "浙江", "江苏"}
        tier2 = {"四川", "湖北", "湖南", "福建", "山东", "河南"}
        if hq_region in tier1:
            region_score = 0.9
            score += 1
            details.append(f"地域 {hq_region} (一线/经济强省) ✓")
        elif hq_region in tier2:
            region_score = 0.6
            score += 0.5
            details.append(f"地域 {hq_region} (中游省份)")
        else:
            region_score = 0.3
            details.append(f"地域 {hq_region} (需关注人口流出风险)")
    else:
        details.append("未设置总部地域")

    # 3. OCF/NI check — computed from last 4 annual reports
    ocf_ni_verdict = "未知"
    from app.models.financial import FinancialStatement
    annual_stmts = (
        db.query(FinancialStatement)
        .filter(
            FinancialStatement.stock_code == code,
            FinancialStatement.report_type == "annual",
        )
        .order_by(FinancialStatement.report_date.desc())
        .limit(4)
        .all()
    )
    if len(annual_stmts) >= 2:
        ocf_sum = sum(s.operating_cash_flow or 0 for s in annual_stmts)
        ni_sum = sum(s.net_profit or 0 for s in annual_stmts)
        if ni_sum > 0:
            ratio = ocf_sum / ni_sum
            if ratio >= 1.2:
                ocf_score = 1.0
                ocf_ni_verdict = "优秀"
                details.append(f"OCF/NI 4年均值 {ratio:.2f} ≥ 1.2 ✓")
            elif ratio >= 1.0:
                ocf_score = 0.7
                ocf_ni_verdict = "良好"
                details.append(f"OCF/NI 4年均值 {ratio:.2f} ≥ 1.0")
            elif ratio >= 0.8:
                ocf_score = 0.3
                ocf_ni_verdict = "尚可"
                details.append(f"OCF/NI 4年均值 {ratio:.2f} ≥ 0.8 (需关注)")
            else:
                ocf_score = 0.0
                ocf_ni_verdict = "警告"
                details.append(f"OCF/NI 4年均值 {ratio:.2f} < 0.8 ✗")
            score += ocf_score
        else:
            details.append("OCF/NI: 净利润为负，无法计算")
    else:
        details.append("OCF/NI: 年报数据不足（需至少2份）")

    # Verdict
    if score >= 2:
        verdict = "可见"
    elif score >= 1:
        verdict = "模糊"
    else:
        verdict = "不可见"

    return BankBlindBox(
        code=code,
        name=stock.name or code,
        dividend_yield=dyr,
        hq_region=hq_region,
        region_score=region_score,
        ocf_ni_verdict=ocf_ni_verdict,
        blind_box_verdict=verdict,
        details=details,
    )
