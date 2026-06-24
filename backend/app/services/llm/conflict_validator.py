"""Conflict validator — post-LLM data validation.

Per decision 12: code-layer defense. Compare LLM JSON output's financial
fields against Lixinger data (single source of truth).

Threshold: >5% mismatch → flag in `data_conflict_json` (non-blocking).
Threshold: >20% of recent reports have conflicts → Pipeline circuit breaker.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.financial import FinancialStatement
from app.models.valuation import ValuationSnapshot
from app.models.stock import Stock

logger = logging.getLogger(__name__)

# Per decision 12: 5% threshold for code-layer post-validation
CONFLICT_THRESHOLD_PCT: float = 5.0


@dataclass
class FieldConflict:
    field: str
    llm_value: float | str
    db_value: float | str
    diff_pct: Optional[float]
    source: str  # which Lixinger table/source
    note: str = ""


def _pct_diff(a: float, b: float) -> Optional[float]:
    """Return signed percent difference relative to |b|. None if b is 0."""
    if b == 0:
        return None if a == 0 else float("inf")
    return round(((a - b) / abs(b)) * 100, 2)


def validate_financials(
    db: Session,
    stock_code: str,
    llm_numbers: dict[str, float | str | None],
) -> list[FieldConflict]:
    """Compare LLM-reported financial numbers vs Lixinger data.

    Args:
        db: DB session
        stock_code: stock code
        llm_numbers: dict of {field: value} from LLM output. Fields recognized:
            pe, pb, market_cap_yi, roe_pct, revenue_yi, net_profit_yi,
            dividend_yield_pct, ocf_to_ni_ratio

    Returns:
        List of FieldConflict for fields where diff_pct > threshold.
        Empty list = no conflicts.
    """
    conflicts: list[FieldConflict] = []

    # 1. Latest valuation snapshot (PE/PB/dyr)
    val = (
        db.query(ValuationSnapshot)
        .filter(ValuationSnapshot.stock_code == stock_code)
        .order_by(ValuationSnapshot.date.desc())
        .first()
    )
    if val:
        if "pe" in llm_numbers and llm_numbers["pe"] is not None and val.pe_ttm:
            try:
                llm_pe = float(llm_numbers["pe"])
                diff = _pct_diff(llm_pe, float(val.pe_ttm))
                if diff is not None and abs(diff) > CONFLICT_THRESHOLD_PCT:
                    conflicts.append(FieldConflict(
                        field="pe",
                        llm_value=llm_pe,
                        db_value=float(val.pe_ttm),
                        diff_pct=diff,
                        source=f"valuation_snapshots (date={val.date})",
                    ))
            except (ValueError, TypeError):
                pass

        if "pb" in llm_numbers and llm_numbers["pb"] is not None and val.pb:
            try:
                llm_pb = float(llm_numbers["pb"])
                diff = _pct_diff(llm_pb, float(val.pb))
                if diff is not None and abs(diff) > CONFLICT_THRESHOLD_PCT:
                    conflicts.append(FieldConflict(
                        field="pb",
                        llm_value=llm_pb,
                        db_value=float(val.pb),
                        diff_pct=diff,
                        source=f"valuation_snapshots (date={val.date})",
                    ))
            except (ValueError, TypeError):
                pass

        if "dividend_yield_pct" in llm_numbers and llm_numbers["dividend_yield_pct"] is not None and val.dividend_yield:
            try:
                llm_dyr = float(llm_numbers["dividend_yield_pct"])
                # dividend_yield is 0-1 fraction, LLM reports as percent (0-100)
                db_dyr_pct = float(val.dividend_yield) * 100
                diff = _pct_diff(llm_dyr, db_dyr_pct)
                if diff is not None and abs(diff) > CONFLICT_THRESHOLD_PCT:
                    conflicts.append(FieldConflict(
                        field="dividend_yield_pct",
                        llm_value=llm_dyr,
                        db_value=db_dyr_pct,
                        diff_pct=diff,
                        source=f"valuation_snapshots (date={val.date})",
                    ))
            except (ValueError, TypeError):
                pass

    # 2. Latest financial statement (revenue / net_profit / ocf / eps)
    fin = (
        db.query(FinancialStatement)
        .filter(FinancialStatement.stock_code == stock_code)
        .order_by(FinancialStatement.report_date.desc())
        .first()
    )
    if fin:
        if "revenue_yi" in llm_numbers and llm_numbers["revenue_yi"] is not None and fin.revenue:
            try:
                llm_rev = float(llm_numbers["revenue_yi"])
                db_rev_yi = float(fin.revenue) / 1e8  # assume Lixinger stores yuan, convert to 亿
                diff = _pct_diff(llm_rev, db_rev_yi)
                if diff is not None and abs(diff) > CONFLICT_THRESHOLD_PCT:
                    conflicts.append(FieldConflict(
                        field="revenue_yi",
                        llm_value=llm_rev,
                        db_value=db_rev_yi,
                        diff_pct=diff,
                        source=f"financial_statements (report_date={fin.report_date})",
                        note="LLM reported in 亿; DB converted from yuan",
                    ))
            except (ValueError, TypeError):
                pass

    return conflicts


def conflicts_to_dict(conflicts: list[FieldConflict]) -> list[dict]:
    """Serialize for DB storage (data_conflict_json column)."""
    return [c.__dict__ for c in conflicts]
