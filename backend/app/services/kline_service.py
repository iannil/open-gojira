"""K-line service — fetch + cache daily candlesticks, derive valuation bands."""

import logging
from datetime import date, timedelta
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.models.price_kline import PriceKline
from app.models.stock import Stock
from app.services.lixinger_client import get_lixinger_client, LixingerError

logger = logging.getLogger(__name__)


def _parse_lx_date(raw) -> Optional[date]:
    if not raw:
        return None
    s = str(raw)[:10]
    try:
        y, m, d = s.split("-")
        return date(int(y), int(m), int(d))
    except (ValueError, IndexError):
        return None


def _fetch_and_persist(
    db: Session,
    stock_code: str,
    start: date,
    end: date,
    freq: str = "day",
) -> int:
    """Pull klines from Lixinger and upsert into the DB. Returns rows touched."""
    client = get_lixinger_client()
    try:
        raw = client.get_kline(
            stock_code=stock_code,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
        )
    except LixingerError:
        logger.warning("Lixinger kline fetch failed for %s %s..%s", stock_code, start, end)
        return 0

    if not raw:
        return 0

    # Build set of existing dates to avoid per-row queries
    existing_dates: set[date] = {
        d for (d,) in db.query(PriceKline.date)
        .filter(
            PriceKline.stock_code == stock_code,
            PriceKline.freq == freq,
            PriceKline.date >= start,
            PriceKline.date <= end,
        )
        .all()
    }

    touched = 0
    for item in raw:
        d = _parse_lx_date(item.get("date"))
        if not d:
            continue
        if d in existing_dates:
            continue
        db.add(PriceKline(
            stock_code=stock_code,
            date=d,
            freq=freq,
            open=item.get("open"),
            high=item.get("high"),
            low=item.get("low"),
            close=item.get("close"),
            volume=item.get("volume"),
            turnover=item.get("amount") or item.get("turnover"),
        ))
        touched += 1

    if touched:
        db.commit()
    return touched


def get_klines(
    db: Session,
    stock_code: str,
    start: Optional[date] = None,
    end: Optional[date] = None,
    freq: str = "day",
    refresh: bool = True,
) -> list[PriceKline]:
    """Return klines for a stock over [start, end], pulling from Lixinger when needed.

    Strategy: check DB first; if window not fully covered (or `refresh=True` and
    last cached date is older than 1 day) pull the missing tail from Lixinger.
    """
    if end is None:
        end = date.today()
    if start is None:
        start = end - timedelta(days=365 * 3)

    # Probe DB coverage
    latest = (
        db.query(PriceKline.date)
        .filter(
            PriceKline.stock_code == stock_code,
            PriceKline.freq == freq,
        )
        .order_by(PriceKline.date.desc())
        .first()
    )

    fetch_start = start
    if latest:
        # Pull only the gap after the latest cached row (with 5-day buffer
        # in case of corrections).
        gap_start = latest[0] - timedelta(days=5)
        if refresh and gap_start <= end:
            fetch_start = max(fetch_start, gap_start)
        elif not refresh:
            fetch_start = end + timedelta(days=1)  # skip fetch

    if fetch_start <= end and refresh:
        _fetch_and_persist(db, stock_code, fetch_start, end, freq=freq)

    rows = (
        db.query(PriceKline)
        .filter(
            PriceKline.stock_code == stock_code,
            PriceKline.freq == freq,
            PriceKline.date >= start,
            PriceKline.date <= end,
        )
        .order_by(PriceKline.date.asc())
        .all()
    )
    return rows


def _quantile(values: list[float], q: float) -> Optional[float]:
    if not values:
        return None
    sv = sorted(values)
    if q <= 0:
        return sv[0]
    if q >= 1:
        return sv[-1]
    idx = q * (len(sv) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(sv) - 1)
    frac = idx - lo
    return sv[lo] * (1 - frac) + sv[hi] * frac


def get_valuation_bands(
    db: Session,
    stock_code: str,
    metric: str = "pe_ttm",
    years: int = 5,
) -> dict:
    """Assemble (date, close, multiple, band-implied prices) for the given metric.

    Bands are P10/P50/P90 quantiles of the actual multiple over the window —
    implying low/median/high price levels at each date via:
        implied_close = close * band_multiple / actual_multiple

    Useful for the "遛狗模型" / valuation band visualization on the frontend.
    """
    if metric not in ("pe_ttm", "pb"):
        raise ValueError(f"unsupported metric {metric}; expected pe_ttm or pb")

    end = date.today()
    start = end - timedelta(days=int(365.25 * years))

    klines = get_klines(db, stock_code, start=start, end=end)

    # Pull historical fundamentals (one Lixinger call covering the full window)
    client = get_lixinger_client()
    try:
        fund_rows = client.get_fundamentals(
            stock_codes=[stock_code],
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            metrics=[metric, "sp"],
        )
    except LixingerError:
        fund_rows = []

    mult_by_date: dict[date, float] = {}
    for r in fund_rows:
        d = _parse_lx_date(r.get("date"))
        v = r.get(metric)
        if d and v is not None:
            mult_by_date[d] = float(v)

    dates: list[str] = []
    close: list[Optional[float]] = []
    actual: list[Optional[float]] = []

    for k in klines:
        dates.append(k.date.isoformat())
        close.append(k.close)
        actual.append(mult_by_date.get(k.date))

    valid_mults = [m for m in actual if m is not None and m > 0]
    p10 = _quantile(valid_mults, 0.1)
    p50 = _quantile(valid_mults, 0.5)
    p90 = _quantile(valid_mults, 0.9)

    band_levels = []
    implied: dict[str, list[Optional[float]]] = {}
    for label, band in (("p10", p10), ("p50", p50), ("p90", p90)):
        if band is None:
            implied[label] = [None] * len(dates)
            continue
        band_levels.append({"label": label, "multiple": round(band, 4)})
        implied[label] = [
            (c * band / m) if (c is not None and m is not None and m > 0) else None
            for c, m in zip(close, actual)
        ]

    return {
        "stock_code": stock_code,
        "metric": metric,
        "dates": dates,
        "close": close,
        "actual_multiple": actual,
        "band_levels": band_levels,
        "implied_close": implied,
    }


# ── prev_close sync ──────────────────────────────────────────────────────


def update_prev_close_for_stock(db: Session, stock_code: str) -> bool:
    """Fetch latest K-line close and store as Stock.prev_close.

    Pulls the most recent 7 calendar days from Lixinger's candlestick
    endpoint and stores the latest close as prev_close. This is the
    reference price for 涨跌停 (price band) validation in trade_service.

    Args:
        db: SQLAlchemy session.
        stock_code: 6-digit A-share stock code.

    Returns:
        True if updated, False if no K-line data available (e.g. newly
        listed, suspended for an extended period, or Lixinger returned
        nothing). prev_close is left unchanged on False.
    """
    client = get_lixinger_client()
    end = date.today().isoformat()
    start = (date.today() - timedelta(days=7)).isoformat()
    try:
        klines = client.get_kline(stock_code, start, end)
    except LixingerError:
        logger.warning("update_prev_close_for_stock: kline fetch failed for %s", stock_code)
        return False

    if not klines:
        return False

    # K-line is returned newest-first (validated in S0 spike).
    latest = klines[0]
    close = latest.get("close")
    if close is None:
        close = latest.get("Close")
    try:
        close_val = float(close) if close is not None else 0.0
    except (TypeError, ValueError):
        close_val = 0.0
    if close_val <= 0:
        return False

    stock = db.get(Stock, stock_code)
    if not stock:
        return False
    stock.prev_close = close_val
    db.flush()
    return True


def update_prev_close_batch(db: Session, stock_codes: Iterable[str]) -> int:
    """Batch update prev_close for multiple stocks.

    Args:
        db: SQLAlchemy session.
        stock_codes: Iterable of 6-digit stock codes.

    Returns:
        Count of successfully updated stocks. Failures are logged but
        do not abort the batch.
    """
    count = 0
    for code in stock_codes:
        try:
            if update_prev_close_for_stock(db, code):
                count += 1
        except Exception as e:
            logger.warning("update_prev_close_batch: failed for %s: %s", code, e)
    db.commit()
    return count
