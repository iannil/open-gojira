"""Index service — sync + query index kline data for benchmark comparison.

Uses Lixinger API to fetch index daily klines (e.g. 沪深300/000300).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core.datetime_utils import now
from app.models.index_kline import IndexKline
from app.services.lixinger_client import LixingerClient

logger = logging.getLogger(__name__)

# 主要基准指数代码
BENCHMARK_CODES: dict[str, str] = {
    "000300": "沪深300",
    "000001": "上证指数",
    "399001": "深证成指",
}

DEFAULT_BENCHMARK = "000300"


def sync_index_klines(db: Session, index_code: str = DEFAULT_BENCHMARK) -> dict:
    """Fetch latest index klines from Lixinger and store to DB.

    Fetches the last 365 days of daily data and inserts/updates rows.
    Idempotent: uses index_code + date unique constraint.

    Returns:
        {"inserted": int, "updated": int, "index_code": str}
    """
    client = LixingerClient()
    end = date.today()
    start = end - timedelta(days=365)

    data = client.get_index_kline(
        stock_code=index_code,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        kline_type="normal",
    )
    if not data or not isinstance(data, list):
        logger.warning("sync_index_klines: no data returned for %s", index_code)
        return {"inserted": 0, "updated": 0, "index_code": index_code}

    inserted = 0
    updated = 0
    for item in data:
        kdate_str = item.get("date")
        if not kdate_str:
            continue
        kdate = date.fromisoformat(kdate_str) if isinstance(kdate_str, str) else kdate_str

        existing = (
            db.query(IndexKline)
            .filter(
                IndexKline.index_code == index_code,
                IndexKline.date == kdate,
            )
            .first()
        )

        if existing:
            existing.open = _float(item.get("open"))
            existing.high = _float(item.get("high"))
            existing.low = _float(item.get("low"))
            existing.close = _float(item.get("close"))
            existing.volume = _float(item.get("volume"))
            updated += 1
        else:
            db.add(IndexKline(
                index_code=index_code,
                date=kdate,
                open=_float(item.get("open")),
                high=_float(item.get("high")),
                low=_float(item.get("low")),
                close=_float(item.get("close")),
                volume=_float(item.get("volume")),
            ))
            inserted += 1

    db.commit()
    logger.info(
        "sync_index_klines: %s inserted=%d updated=%d",
        index_code, inserted, updated,
    )
    return {"inserted": inserted, "updated": updated, "index_code": index_code}


def get_index_kline_range(
    db: Session,
    index_code: str = DEFAULT_BENCHMARK,
    *,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> list[IndexKline]:
    """Get index klines for a date range, ordered by date ascending."""
    q = db.query(IndexKline).filter(IndexKline.index_code == index_code)
    if start_date:
        q = q.filter(IndexKline.date >= start_date)
    if end_date:
        q = q.filter(IndexKline.date <= end_date)
    return q.order_by(IndexKline.date.asc()).all()


def compute_benchmark_return(
    db: Session,
    index_code: str = DEFAULT_BENCHMARK,
    *,
    start_date: date,
    end_date: Optional[date] = None,
) -> Optional[float]:
    """Compute total return of an index over a period.

    Uses close-to-close returns. Returns decimal (e.g. 0.05 = 5%).
    Returns None if data is insufficient.
    """
    end_date = end_date or date.today()
    klines = get_index_kline_range(db, index_code, start_date=start_date, end_date=end_date)
    if len(klines) < 2:
        return None
    start_close = klines[0].close
    end_close = klines[-1].close
    if not start_close or not end_close or start_close == 0:
        return None
    return (end_close - start_close) / start_close


def _float(v) -> Optional[float]:
    if v is None:
        return None
    return float(v)
