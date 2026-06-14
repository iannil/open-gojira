"""Historical data pipeline — fetch 10y time-series from Lixinger.

Three fetchers (klines / valuations / financials) + batch orchestrator.
Designed for partial sync (selected stocks only) to stay within Lixinger
quota. Idempotent via upsert on unique constraint.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.historical_financial import HistoricalFinancial
from app.models.historical_kline import HistoricalKline
from app.models.historical_valuation import HistoricalValuation
from app.services.lixinger_client import get_lixinger_client


logger = logging.getLogger(__name__)


# --- K-lines ---


def fetch_and_upsert_klines(
    db: Session,
    stock_code: str,
    start_date: str,
    end_date: str,
) -> int:
    """Fetch daily K-line series from Lixinger and upsert into historical_klines.

    Returns count of newly inserted rows (skipped rows not counted).
    """
    client = get_lixinger_client()
    try:
        records = client.get_kline(stock_code, start_date, end_date)
    except Exception as e:
        logger.error("K-line fetch failed for %s: %s", stock_code, e)
        raise

    inserted = 0
    for r in records or []:
        try:
            d = _parse_date(r.get("date"))
            if not d:
                continue
            existing = db.execute(
                select(HistoricalKline).where(
                    HistoricalKline.stock_code == stock_code,
                    HistoricalKline.date == d,
                )
            ).scalar_one_or_none()
            if existing:
                continue  # upsert skip
            kline = HistoricalKline(
                stock_code=stock_code,
                date=d,
                open=float(r["open"]),
                high=float(r["high"]),
                low=float(r["low"]),
                close=float(r["close"]),
                volume=_safe_float(r.get("volume")),
                amount=_safe_float(r.get("amount")),
                turnover_rate=_safe_float(r.get("to_r")),
            )
            db.add(kline)
            inserted += 1
        except (KeyError, ValueError, TypeError) as e:
            logger.warning("Skip kline %s %s: %s", stock_code, r.get("date"), e)
    db.flush()
    return inserted


# --- Valuations ---


def fetch_and_upsert_valuations(
    db: Session,
    stock_code: str,
    start_date: str,
    end_date: str,
) -> int:
    """Fetch valuation time-series (PE/PB/PS/DYR/MC) and upsert."""
    client = get_lixinger_client()
    try:
        records = client.get_fundamentals(
            [stock_code],
            start_date=start_date,
            end_date=end_date,
            metrics=[
                "pe_ttm", "pb", "pb_wo_gw", "ps_ttm", "pcf_ttm",
                "dyr", "sp", "mc", "mc_om", "cmc",
            ],
        )
    except Exception as e:
        logger.error("Valuation fetch failed for %s: %s", stock_code, e)
        raise

    inserted = 0
    for r in records or []:
        try:
            d = _parse_date(r.get("date"))
            if not d:
                continue
            existing = db.execute(
                select(HistoricalValuation).where(
                    HistoricalValuation.stock_code == stock_code,
                    HistoricalValuation.date == d,
                )
            ).scalar_one_or_none()
            if existing:
                continue
            val = HistoricalValuation(
                stock_code=stock_code,
                date=d,
                pe_ttm=_safe_float(r.get("pe_ttm")),
                pb=_safe_float(r.get("pb")),
                pb_wo_gw=_safe_float(r.get("pb_wo_gw")),
                ps_ttm=_safe_float(r.get("ps_ttm")),
                pcf_ttm=_safe_float(r.get("pcf_ttm")),
                dyr=_safe_float(r.get("dyr")),
                sp=_safe_float(r.get("sp")),
                mc=_safe_float(r.get("mc")),
                mc_om=_safe_float(r.get("mc_om")),
                cmc=_safe_float(r.get("cmc")),
            )
            db.add(val)
            inserted += 1
        except (KeyError, ValueError, TypeError) as e:
            logger.warning("Skip val %s %s: %s", stock_code, r.get("date"), e)
    db.flush()
    return inserted


# --- Financials ---


def fetch_and_upsert_financials(
    db: Session,
    stock_code: str,
    start_date: str,
    end_date: str,
) -> int:
    """Fetch financial statements (quarterly + annual) and upsert.

    Iterates granularity in (q, y). Each Lixinger call returns period
    records; period (date field) is the natural unique key.

    Note: Lixinger returns financial data in a NESTED structure keyed by
    granularity (q/y) → section (bs/ps/cfs/m) → field → {"t": value}.
    We walk that structure via _nested_financial_value(); the prior flat
    `r.get("ps.toi.t")` lookups always returned None.
    """
    client = get_lixinger_client()
    inserted = 0
    # Track inserted periods in-process: db session is autoflush=False,
    # so pending rows are invisible to a subsequent SELECT. Tracking here
    # prevents double-INSERT when q and y endpoints overlap on the same
    # period (or when the API returns the same row across both calls).
    seen_periods: set[tuple[str, date]] = set()
    for granularity in ("q", "y"):
        try:
            records = client.get_financials(
                stock_code,
                start_date=start_date,
                end_date=end_date,
                granularity=granularity,
            )
        except Exception as e:
            logger.error(
                "Financial fetch failed for %s (%s): %s",
                stock_code, granularity, e,
            )
            continue
        for r in records or []:
            try:
                period = _parse_date(r.get("date"))
                report_date = _parse_date(r.get("reportDate"))
                if not period or not report_date:
                    continue
                key = (stock_code, period)
                if key in seen_periods:
                    continue
                existing = db.execute(
                    select(HistoricalFinancial).where(
                        HistoricalFinancial.stock_code == stock_code,
                        HistoricalFinancial.period == period,
                    )
                ).scalar_one_or_none()
                if existing:
                    seen_periods.add(key)
                    continue
                fin = HistoricalFinancial(
                    stock_code=stock_code,
                    period=period,
                    report_date=report_date,
                    report_type=r.get("reportType"),
                    revenue=_nested_financial_value(r, granularity, "ps", "toi"),
                    net_profit=_nested_financial_value(r, granularity, "ps", "np"),
                    operating_profit=_nested_financial_value(r, granularity, "ps", "oi"),
                    total_assets=_nested_financial_value(r, granularity, "bs", "ta"),
                    total_liabilities=_nested_financial_value(r, granularity, "bs", "tl"),
                    total_equity=_nested_financial_value(r, granularity, "bs", "toe"),
                    operating_cash_flow=_nested_financial_value(r, granularity, "cfs", "ncffoa"),
                    investing_cash_flow=_nested_financial_value(r, granularity, "cfs", "ncffia"),
                    financing_cash_flow=_nested_financial_value(r, granularity, "cfs", "ncfffa"),
                    roe=_nested_financial_value(r, granularity, "m", "wroe"),
                    roa=_nested_financial_value(r, granularity, "m", "roa"),
                    debt_ratio=_nested_financial_value(r, granularity, "m", "tl_ta_r"),
                    ocf_to_np_ratio=_nested_financial_value(r, granularity, "m", "ncffoa_np_r"),
                    gross_margin=_nested_financial_value(r, granularity, "m", "gp_m"),
                )
                db.add(fin)
                seen_periods.add(key)
                inserted += 1
            except (KeyError, ValueError, TypeError) as e:
                logger.warning(
                    "Skip fin %s %s: %s", stock_code, r.get("date"), e
                )
        db.flush()
    return inserted


def _nested_financial_value(
    record: dict, granularity: str, section: str, field: str,
) -> float | None:
    """Walk Lixinger's nested financial response: record[g][section][field][t].

    Lixinger returns financials as nested dicts, e.g.:
        {"q": {"ps": {"toi": {"t": 70987206095}}}}
    Metrics are requested with a granularity prefix ("q.bs.ta.t") but the
    response collapses them into nested form. This helper walks that tree.

    Returns None if any level is missing or value is non-numeric.
    """
    bucket = record.get(granularity)
    if not isinstance(bucket, dict):
        return None
    section_data = bucket.get(section)
    if not isinstance(section_data, dict):
        return None
    field_data = section_data.get(field)
    if not isinstance(field_data, dict):
        return None
    return _safe_float(field_data.get("t"))


# --- Batch orchestrator ---


def run_historical_sync(
    db: Session,
    stock_codes: Iterable[str],
    start_date: str = "2015-01-01",
    end_date: str | None = None,
) -> dict[str, int]:
    """Run all 3 fetchers for each stock. Returns summary counts.

    Per-stock errors caught and counted; batch continues so one bad
    stock doesn't block others. Suitable for partial sync of selected
    stocks (holdings + watchlist + candidates + plan scope).
    """
    end_date = end_date or date.today().isoformat()
    codes = list(stock_codes)

    summary = {"klines": 0, "valuations": 0, "financials": 0, "errors": 0}

    for code in codes:
        for kind, fetcher in [
            ("klines", fetch_and_upsert_klines),
            ("valuations", fetch_and_upsert_valuations),
            ("financials", fetch_and_upsert_financials),
        ]:
            try:
                count = fetcher(db, code, start_date, end_date)
                summary[kind] += count
            except Exception as e:
                logger.warning("Failed %s for %s: %s", kind, code, e)
                summary["errors"] += 1

    db.commit()
    return summary


# --- Helpers ---


def _parse_date(s: str | None) -> date | None:
    """Parse a YYYY-MM-DD string (or any 10-char prefix) into a date.

    Returns None on missing/invalid input — caller decides what to do.
    """
    if not s or not isinstance(s, str):
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _safe_float(v) -> float | None:
    """Coerce to float, returning None for NaN/inf/None/unparseable.

    Lixinger occasionally returns NaN or null for missing metric values;
    HistoricalValuation/Financial columns are nullable so we propagate None.
    """
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f
