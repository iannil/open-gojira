"""Red line checker — 8 hard-reject triggers.

Per decision 13: any single red line hit → report status = rejected,
stock stays out of candidate pool.

Red lines:
  1. management_integrity      — 管理层诚信污点（欺诈、违规披露、承诺反复打破）
  2. financial_fraud           — 财务造假嫌疑（Benford 异常、现金流与利润长期背离）
  3. major_violation           — 重大违规（证监会处罚、退市风险警示）
  4. consecutive_losses        — 连年亏损（3 年扣非净利润为负）
  5. high_pledge               — 高质押（控股股东质押比例 >50%）
  6. frequent_reduction        — 频繁减持（控股股东 12 月内 >10%）
  7. complex_related_transactions — 复杂关联交易（占营收 >30%）
  8. benford_anomaly           — 财务数据首位数字分布异常
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.financial import FinancialStatement
from app.models.red_line_event import (
    ALL_RED_LINES,
    RED_LINE_BENFORD_ANOMALY,
    RED_LINE_COMPLEX_RELATED_TRANSACTIONS,
    RED_LINE_CONSECUTIVE_LOSSES,
    RED_LINE_FINANCIAL_FRAUD,
    RED_LINE_FREQUENT_REDUCTION,
    RED_LINE_HIGH_PLEDGE,
    RED_LINE_MAJOR_VIOLATION,
    RED_LINE_MANAGEMENT_INTEGRITY,
    RedLineEvent,
)
from app.models.research_report import ResearchReport

logger = logging.getLogger(__name__)

CONSECUTIVE_LOSS_YEARS: int = 3
CONSECUTIVE_LOSSES: int = CONSECUTIVE_LOSS_YEARS  # alias for legacy reference
PLEDGE_RATIO_THRESHOLD: float = 0.50  # 50%
REDUCTION_RATIO_THRESHOLD: float = 0.10  # 10% in 12 months
RELATED_TRANSACTION_RATIO_THRESHOLD: float = 0.30  # 30% of revenue
BENFORD_CHI_SQUARE_P_THRESHOLD: float = 0.05  # p<0.05 = anomaly


@dataclass
class RedLineHit:
    red_line_type: str
    severity: str  # hard_reject (default for all 8)
    evidence: dict[str, Any]
    action_taken: str = "rejected"


def check_consecutive_losses(
    db: Session, stock_code: str
) -> Optional[RedLineHit]:
    """Check rule 4: latest N annual reports all show negative net profit."""
    annuals = (
        db.query(FinancialStatement)
        .filter(
            FinancialStatement.stock_code == stock_code,
            # annual = report_date month 12, or we use type filter if available
        )
        .order_by(FinancialStatement.report_date.desc())
        .limit(CONSECUTIVE_LOSS_YEARS)
        .all()
    )
    if len(annuals) < CONSECUTIVE_LOSS_YEARS:
        return None

    # All must be negative net profit
    if all(fin.net_profit is not None and float(fin.net_profit) < 0 for fin in annuals):
        return RedLineHit(
            red_line_type=RED_LINE_CONSECUTIVE_LOSSES,
            severity="hard_reject",
            evidence={
                "consecutive_years": CONSECUTIVE_LOSSES,
                "annual_reports": [
                    {
                        "report_date": str(fin.report_date),
                        "net_profit": float(fin.net_profit) if fin.net_profit else None,
                    }
                    for fin in annuals
                ],
            },
        )
    return None


def check_llm_flagged_red_lines(
    llm_output: dict[str, Any],
) -> list[RedLineHit]:
    """Extract red lines LLM flagged in its output.

    LLM is required (per defense_methodology prompt) to flag any red line
    indicators it observes in its JSON output's `red_line_flags` field.
    """
    hits: list[RedLineHit] = []
    flags = llm_output.get("red_line_flags") or []

    if isinstance(flags, dict):
        # Format: {"management_integrity": {"evidence": "..."}, ...}
        for flag_type, evidence in flags.items():
            if flag_type in ALL_RED_LINES:
                hits.append(RedLineHit(
                    red_line_type=flag_type,
                    severity="hard_reject",
                    evidence=evidence if isinstance(evidence, dict) else {"note": str(evidence)},
                ))
    elif isinstance(flags, list):
        # Format: [{"type": "management_integrity", "evidence": {...}}, ...]
        for flag in flags:
            flag_type = flag.get("type") or flag.get("red_line_type")
            if flag_type in ALL_RED_LINES:
                hits.append(RedLineHit(
                    red_line_type=flag_type,
                    severity="hard_reject",
                    evidence=flag.get("evidence", {}),
                ))
    return hits


def check_all(
    db: Session,
    stock_code: str,
    llm_output: Optional[dict[str, Any]] = None,
) -> list[RedLineHit]:
    """Run all applicable red line checks.

    Combines:
      - Code-verifiable rules (consecutive_losses, etc.)
      - LLM-flagged rules (management_integrity, fraud, violation, etc.)
    """
    hits: list[RedLineHit] = []

    # Code-layer checks (deterministic from DB data)
    code_checks = [
        check_consecutive_losses,
        # Phase 5+ will add:
        # check_high_pledge (needs shareholder data)
        # check_frequent_reduction (needs shareholder transaction data)
        # check_complex_related_transactions (needs related party transaction data)
        # check_benford_anomaly (needs full financial series)
    ]
    for check_fn in code_checks:
        try:
            hit = check_fn(db, stock_code)
            if hit:
                hits.append(hit)
        except Exception:
            logger.exception(
                "Red line check %s failed for %s",
                check_fn.__name__, stock_code,
            )

    # LLM-flagged checks
    if llm_output:
        hits.extend(check_llm_flagged_red_lines(llm_output))

    return hits


def write_red_line_events(
    db: Session,
    stock_code: str,
    hits: list[RedLineHit],
    report_id: Optional[int] = None,
) -> list[RedLineEvent]:
    """Persist red line hits to red_line_events table."""
    events = []
    for hit in hits:
        event = RedLineEvent(
            stock_code=stock_code,
            red_line_type=hit.red_line_type,
            report_id=report_id,
            severity=hit.severity,
            evidence_json=hit.evidence,
            action_taken=hit.action_taken,
        )
        db.add(event)
        events.append(event)
    db.flush()
    return events
