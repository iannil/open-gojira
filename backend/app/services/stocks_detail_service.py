"""Stock detail service — wraps Lixinger raw APIs that were already
encapsulated in lixinger_client but not yet exposed via routers.

Covers: majority shareholders, north-bound capital, margin trading.
"""

import logging
from datetime import date, timedelta
from typing import Optional

from app.services.lixinger_client import LixingerError, get_lixinger_client

logger = logging.getLogger(__name__)


def _default_start(days: int = 365) -> str:
    return (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")


def get_majority_shareholders(stock_code: str, days: int = 730) -> list[dict]:
    """Return recent top-10 shareholder snapshots (default ~2 years)."""
    try:
        client = get_lixinger_client()
        raw = client.get_majority_shareholders(stock_code, start_date=_default_start(days))
    except LixingerError:
        logger.exception("Failed to fetch shareholders for %s", stock_code)
        return []

    results: list[dict] = []
    for item in raw or []:
        ds = str(item.get("date", ""))[:10]
        holders = item.get("majorityShareholders") or item.get("shareholders") or []
        for h in holders:
            results.append(
                {
                    "date": ds,
                    "holder_name": h.get("name") or h.get("holderName"),
                    "holder_type": h.get("type") or h.get("holderType"),
                    "holding_quantity": _to_float(h.get("holdingQuantity") or h.get("quantity")),
                    "holding_ratio": _to_float(h.get("holdingRatio") or h.get("ratio")),
                }
            )
    return results


def get_north_flow(stock_code: str, days: int = 60) -> list[dict]:
    """Return northbound (互联互通) flow records for a single stock."""
    try:
        client = get_lixinger_client()
        raw = client.get_mutual_market(stock_code, start_date=_default_start(days))
    except LixingerError:
        logger.exception("Failed to fetch north flow for %s", stock_code)
        return []

    results: list[dict] = []
    for item in raw or []:
        results.append(
            {
                "date": str(item.get("date", ""))[:10],
                "net_buy_amount": _to_float(item.get("netBuyAmount") or item.get("net_buy")),
                "holding_quantity": _to_float(item.get("holdingQuantity") or item.get("holding")),
                "holding_ratio": _to_float(item.get("holdingRatio")),
            }
        )
    return results


def get_revenue_composition(stock_code: str, years: int = 5) -> list[dict]:
    """Return revenue composition (business segments) for recent N years.

    Lixinger response shape varies by company; this helper normalises to:
    [
      {"date": "2023-12-31", "segments": [
          {"name": "白酒", "revenue": 12345.0, "ratio": 0.85},
          ...
      ]},
      ...
    ]
    """
    try:
        client = get_lixinger_client()
        start = (date.today() - timedelta(days=years * 365)).strftime("%Y-%m-%d")
        raw = client.get_revenue_composition(stock_code, start_date=start)
    except LixingerError:
        logger.exception("Failed to fetch revenue composition for %s", stock_code)
        return []

    grouped: dict[str, list[dict]] = {}
    for item in raw or []:
        d = str(item.get("date", ""))[:10]
        if not d:
            continue
        # Try multiple shapes from Lixinger
        segments = (
            item.get("composition")
            or item.get("segments")
            or item.get("items")
            or []
        )
        normalised = []
        for seg in segments:
            normalised.append(
                {
                    "name": seg.get("name") or seg.get("segmentName"),
                    "category": seg.get("category") or seg.get("type"),
                    "revenue": _to_float(seg.get("revenue") or seg.get("amount")),
                    "ratio": _to_float(seg.get("ratio") or seg.get("proportion")),
                }
            )
        grouped.setdefault(d, []).extend(normalised)

    results = [
        {"date": d, "segments": segs}
        for d, segs in sorted(grouped.items(), reverse=True)
    ]
    return results


def get_margin_trading(stock_code: str, days: int = 60) -> list[dict]:
    """Return margin trading (融资融券) records for a single stock."""
    try:
        client = get_lixinger_client()
        raw = client.get_margin_trading(stock_code, start_date=_default_start(days))
    except LixingerError:
        logger.exception("Failed to fetch margin for %s", stock_code)
        return []

    results: list[dict] = []
    for item in raw or []:
        results.append(
            {
                "date": str(item.get("date", ""))[:10],
                "financing_balance": _to_float(item.get("financingBalance")),
                "securities_balance": _to_float(item.get("securitiesBalance")),
                "net_financing": _to_float(item.get("netFinancingBuy") or item.get("netFinancing")),
            }
        )
    return results


def get_shareholders_num(stock_code: str, years: int = 3) -> list[dict]:
    """Return shareholder-count history (筹码集中度)."""
    try:
        client = get_lixinger_client()
        raw = client.get_shareholders_num(stock_code, start_date=_default_start(int(365.25 * years)))
    except LixingerError:
        logger.exception("Failed to fetch shareholders_num for %s", stock_code)
        return []
    return [
        {
            "date": str(item.get("date", ""))[:10],
            "shareholders_num": _to_float(item.get("shareholdersNum") or item.get("num")),
            "avg_holding_value": _to_float(item.get("avgHoldingValue")),
        }
        for item in raw or []
    ]


def get_customers(stock_code: str, years: int = 5) -> list[dict]:
    """Return major-customer history (上游议价)."""
    try:
        client = get_lixinger_client()
        raw = client.get_customers(stock_code, start_date=_default_start(int(365.25 * years)))
    except LixingerError:
        logger.exception("Failed to fetch customers for %s", stock_code)
        return []
    return raw or []


def get_suppliers(stock_code: str, years: int = 5) -> list[dict]:
    """Return major-supplier history (下游议价)."""
    try:
        client = get_lixinger_client()
        raw = client.get_suppliers(stock_code, start_date=_default_start(int(365.25 * years)))
    except LixingerError:
        logger.exception("Failed to fetch suppliers for %s", stock_code)
        return []
    return raw or []


def _to_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
