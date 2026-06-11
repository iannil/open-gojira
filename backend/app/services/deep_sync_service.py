"""Deep sync service — sync financials, klines, dividends for candidates and high-dyr stocks."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.candidate import Candidate
from app.models.dividend import DividendRecord
from app.models.financial import FinancialStatement
from app.models.price_kline import PriceKline
from app.models.valuation import ValuationSnapshot

logger = logging.getLogger(__name__)

# Minimum dividend yield threshold for deep sync eligibility
_DYR_THRESHOLD = 0.03


def _get_high_dyr_codes(db: Session) -> set[str]:
    """Get stock codes with dyr >= threshold in the latest valuation snapshot."""
    from sqlalchemy import func

    latest_date = db.execute(
        select(func.max(ValuationSnapshot.date))
    ).scalar()
    if not latest_date:
        return set()

    rows = db.execute(
        select(ValuationSnapshot.stock_code)
        .where(
            ValuationSnapshot.date == latest_date,
            ValuationSnapshot.dividend_yield >= _DYR_THRESHOLD,
        )
    ).scalars().all()
    return set(rows)


def _filter_needing_sync(db: Session, codes: list[str]) -> list[str]:
    """Filter codes that lack at least one deep-tier data type."""
    if not codes:
        return []

    has_fin = {
        r[0] for r in db.execute(
            select(FinancialStatement.stock_code)
            .where(FinancialStatement.stock_code.in_(codes))
            .distinct()
        ).all()
    }
    has_kline = {
        r[0] for r in db.execute(
            select(PriceKline.stock_code)
            .where(PriceKline.stock_code.in_(codes))
            .distinct()
        ).all()
    }
    has_div = {
        r[0] for r in db.execute(
            select(DividendRecord.stock_code)
            .where(DividendRecord.stock_code.in_(codes))
            .distinct()
        ).all()
    }

    return [
        c for c in codes
        if c not in has_fin or c not in has_kline or c not in has_div
    ]


def get_candidate_codes_needing_deep_sync(db: Session) -> list[str]:
    """Get active candidate codes that lack deep-tier data."""
    active_candidates = db.execute(
        select(Candidate.stock_code)
        .where(Candidate.status == "active")
        .distinct()
    ).all()
    codes = [c[0] for c in active_candidates]
    return _filter_needing_sync(db, codes)


def sync_candidates_deep_data(db: Session) -> dict:
    """Trigger deep sync (financials + klines + dividends) for candidates and high-dyr stocks."""
    from app.services.pipelines.manager import PipelineManager

    # Collect codes from candidates and high-dyr stocks
    candidate_codes = {
        c[0] for c in db.execute(
            select(Candidate.stock_code)
            .where(Candidate.status == "active")
            .distinct()
        ).all()
    }
    high_dyr_codes = _get_high_dyr_codes(db)
    all_codes = list(candidate_codes | high_dyr_codes)

    codes = _filter_needing_sync(db, all_codes)
    if not codes:
        logger.info("deep_sync: no stocks need deep data")
        return {"synced": 0, "codes": 0}

    logger.info(
        "deep_sync: syncing deep data for %d stocks (candidates=%d, high_dyr=%d)",
        len(codes), len(candidate_codes), len(high_dyr_codes),
    )
    mgr = PipelineManager(db)

    results = {}
    for pipeline_type in ("financials", "klines", "dividends"):
        try:
            r = mgr.start(
                pipeline_type=pipeline_type,
                stock_codes=codes,
                background=False,
            )
            results[pipeline_type] = r
        except Exception as e:
            logger.exception("deep_sync: %s pipeline failed", pipeline_type)
            results[pipeline_type] = {"error": str(e)}

    return {"synced": len(codes), "codes": len(codes), "details": results}
