"""Data fetching service — wraps Lixinger API for stock data.

Replaces the former AKShare-based service. All data comes from Lixinger.
"""

import json
import logging
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.stock import Stock
from app.models.valuation import ValuationSnapshot
from app.services.lixinger_client import get_lixinger_client, LixingerError

logger = logging.getLogger(__name__)


def stock_to_response(stock: Stock, db: Session) -> dict:
    """Convert a Stock ORM object to a response dict with computed fields."""
    latest_val_date: Optional[date] = None
    if stock.valuations:
        dates = [v.date for v in stock.valuations if v.date]
        if dates:
            latest_val_date = max(dates)
    else:
        result = (
            db.query(func.max(ValuationSnapshot.date))
            .filter(ValuationSnapshot.stock_code == stock.code)
            .scalar()
        )
        latest_val_date = result

    # Parse thesis_variables_json
    thesis_variables = None
    if stock.thesis_variables_json:
        try:
            thesis_variables = json.loads(stock.thesis_variables_json)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Failed to parse thesis_variables_json for %s", stock.code)
            thesis_variables = None

    qiu_detail = None
    if stock.qiu_detail_json:
        try:
            qiu_detail = json.loads(stock.qiu_detail_json)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Failed to parse qiu_detail_json for %s", stock.code)
            qiu_detail = None

    return {
        "code": stock.code,
        "name": stock.name,
        "industry": stock.industry,
        "listed_date": stock.listed_date,
        "qiu_score": stock.qiu_score,
        "qiu_detail": qiu_detail,
        "security_theme": stock.security_theme,
        "tier": stock.tier,
        "notes": stock.notes,
        "thesis_variables": thesis_variables,
        "created_at": stock.created_at,
        "updated_at": stock.updated_at,
        "latest_valuation_date": latest_val_date,
    }


def fetch_stock_info(code: str) -> Optional[dict]:
    """Fetch stock name and industry from Lixinger.

    Args:
        code: Stock code, e.g. "600519".

    Returns:
        {"code": ..., "name": ..., "industry": ...} or None.
    """
    try:
        client = get_lixinger_client()
        # Try direct profile lookup first (faster for single stock)
        profile = client.get_company_profile(code)
        if profile:
            return {
                "code": code,
                "name": profile.get("name", ""),
                "industry": profile.get("industry", ""),
            }

        # Fallback: search in full company list (auto-paginated, cached 24h)
        # get_company_list_all loops past Lixinger's silent 500-record cap,
        # so the fallback actually sees the full 5625-share universe rather
        # than the 500-row subset the legacy get_company_list returned.
        companies = client.get_company_list_all()
        for c in companies:
            if c.get("stockCode") == code:
                return {
                    "code": code,
                    "name": c.get("name", ""),
                    "industry": "",
                }
        return None
    except LixingerError:
        logger.exception("Failed to fetch stock info for %s", code)
        return None


def fetch_pe_pb_history(code: str, years: int = 10) -> list[dict]:
    """Fetch historical daily PE/PB data from Lixinger.

    Args:
        code: Stock code.
        years: How many years of history to return.

    Returns:
        List of {"date": str, "pe_ttm": float, "pb": float}.
        Empty list on error.
    """
    try:
        client = get_lixinger_client()
        start = (date.today() - timedelta(days=years * 365)).strftime("%Y-%m-%d")
        end = date.today().strftime("%Y-%m-%d")

        data = client.get_fundamentals(
            stock_codes=[code],
            start_date=start,
            end_date=end,
            metrics=["pe_ttm", "pb"],
        )
        if not data:
            return []

        result = []
        for item in data:
            pe = item.get("pe_ttm")
            pb = item.get("pb")
            d = item.get("date", "")
            if d:
                result.append({
                    "date": d[:10],
                    "pe_ttm": float(pe) if pe is not None else 0,
                    "pb": float(pb) if pb is not None else 0,
                })
        return result
    except LixingerError:
        logger.exception("Failed to fetch PE/PB history for %s", code)
        return []


def fetch_current_price(code: str) -> Optional[float]:
    """Fetch the latest price for a stock from Lixinger.

    Args:
        code: Stock code.

    Returns:
        Latest price as float, or None if unavailable.
    """
    try:
        client = get_lixinger_client()
        data = client.get_fundamentals(
            stock_codes=[code],
            metrics=["sp"],
        )
        if not data:
            return None
        price = data[0].get("sp")
        return float(price) if price is not None else None
    except LixingerError:
        logger.exception("Failed to fetch current price for %s", code)
        return None


