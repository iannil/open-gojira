"""Sync corporate actions from Lixinger + heuristic delist detection.

Lixinger dividend endpoint returns cash + stock dividends + capitalization
in one record per ex-date. We split mixed records into multiple CorpAction
rows (one per action_type) for clean processing.

Delistings: Lixinger has no endpoint. We detect by diffing the company
list — if a stock_code in our DB disappears from /cn/company, fetch its
profile and parse historyStockNames for the name change to "退市..." or
"*ST..." to extract the delist date.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.corp_action import CorpAction
from app.models.stock import Stock
from app.services.lixinger_client import get_lixinger_client
from app.core.datetime_utils import now


logger = logging.getLogger(__name__)


def _parse_dividend_record(
    stock_code: str, record: dict
) -> list[dict] | None:
    """Parse one Lixinger dividend record into one or more CorpAction dicts.

    Returns list because mixed records (e.g. 10送5派25) produce multiple
    actions. Returns None if record has no actual distribution.
    """
    ex_date_str = record.get("exDate") or record.get("date")
    if not ex_date_str:
        return None
    try:
        ex_date = datetime.strptime(ex_date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None

    actions: list[dict] = []
    cash = record.get("dividend") or 0
    stock_bonus = record.get("bonusSharesFromProfit") or 0
    cap_reserve = record.get("bonusSharesFromCapitalReserve") or 0
    record_date = record.get("registerDate")
    payment_date = record.get("paymentDate")

    try:
        cash_f = float(cash) if cash else 0.0
        stock_f = float(stock_bonus) if stock_bonus else 0.0
        cap_f = float(cap_reserve) if cap_reserve else 0.0
    except (ValueError, TypeError):
        logger.warning("Bad numeric fields in dividend record %s: %s",
                       stock_code, record)
        return None

    if cash_f > 0:
        actions.append({
            "stock_code": stock_code,
            "ex_date": ex_date,
            "action_type": "cash_dividend",
            "params_json": {
                "per_share": cash_f,
                "record_date": record_date,
                "payment_date": payment_date,
            },
            "source": "lixinger",
        })

    if stock_f > 0:
        actions.append({
            "stock_code": stock_code,
            "ex_date": ex_date,
            "action_type": "stock_dividend",
            "params_json": {
                "per_10_shares": stock_f,
                "record_date": record_date,
            },
            "source": "lixinger",
        })

    if cap_f > 0:
        actions.append({
            "stock_code": stock_code,
            "ex_date": ex_date,
            "action_type": "capitalization",
            "params_json": {
                "per_10_shares": cap_f,
                "record_date": record_date,
            },
            "source": "lixinger",
        })

    return actions if actions else None


def _is_existing(db: Session, stock_code: str, ex_date: date,
                 action_type: str, source: str) -> bool:
    return db.execute(
        select(CorpAction.id).where(
            CorpAction.stock_code == stock_code,
            CorpAction.ex_date == ex_date,
            CorpAction.action_type == action_type,
            CorpAction.source == source,
        ).limit(1)
    ).first() is not None


def sync_dividends_for_stock(
    db: Session,
    stock_code: str,
    start_date: str = "2015-01-01",
    end_date: str | None = None,
) -> int:
    """Sync dividend history for one stock. Returns count of new records."""
    end_date = end_date or date.today().isoformat()
    try:
        client = get_lixinger_client()
        records = client.get_dividend_full(stock_code, start_date, end_date)
    except Exception as e:
        logger.error("Failed to fetch dividends for %s: %s", stock_code, e)
        return 0

    inserted = 0
    for record in records or []:
        parsed = _parse_dividend_record(stock_code, record)
        if not parsed:
            continue
        for action_data in parsed:
            if _is_existing(db, action_data["stock_code"], action_data["ex_date"],
                            action_data["action_type"], action_data["source"]):
                continue
            db.add(CorpAction(**action_data))
            inserted += 1
    db.flush()
    return inserted


def sync_dividends_batch(
    db: Session, stock_codes: Iterable[str]
) -> int:
    """Batch sync dividends for multiple stocks."""
    total = 0
    for code in stock_codes:
        try:
            n = sync_dividends_for_stock(db, code)
            total += n
        except Exception as e:
            logger.warning("Dividend sync failed for %s: %s", code, e)
    db.commit()
    return total


def detect_delistings(db: Session) -> list[CorpAction]:
    """Find stocks in DB that disappeared from Lixinger's company list.

    For each missing stock, fetch profile.historyStockNames and look for
    rename to '退市...' or '*ST...' to extract delist date.

    Returns list of newly created CorpAction rows (action_type='delist').
    """
    client = get_lixinger_client()
    try:
        lixinger_codes = {
            r.get("stockCode") for r in client.get_company_list_all()
            if r.get("stockCode")
        }
    except Exception as e:
        logger.error("Failed to fetch company list for delist detection: %s", e)
        return []

    # Get stocks that exist in our DB
    db_codes = set(db.execute(select(Stock.code)).scalars().all())

    # Missing = in DB but not in Lixinger
    missing_codes = db_codes - lixinger_codes
    if not missing_codes:
        return []

    new_actions: list[CorpAction] = []
    for code in missing_codes:
        # Check if we already have a delist action
        existing = db.execute(
            select(CorpAction).where(
                CorpAction.stock_code == code,
                CorpAction.action_type == "delist",
            ).limit(1)
        ).scalar_one_or_none()
        if existing:
            continue

        # Fetch profile to find delist date
        try:
            profile = client.get_company_profile(code) or {}
        except Exception as e:
            logger.warning("Profile fetch failed for missing stock %s: %s", code, e)
            continue

        history_names = profile.get("historyStockNames") or []
        delist_date, new_name = _find_delist_in_history(history_names)
        if not delist_date:
            logger.info("Stock %s missing from Lixinger but no delist "
                        "evidence in historyStockNames; skipping", code)
            continue

        action = CorpAction(
            stock_code=code,
            ex_date=delist_date,
            action_type="delist",
            params_json={
                "new_name": new_name,
                "history_names": history_names,
                "detected_at": now().isoformat(),
            },
            source="heuristic",
            note="Detected by company list diff + profile.historyStockNames",
        )
        db.add(action)
        new_actions.append(action)

    db.flush()
    return new_actions


def _find_delist_in_history(
    history_names: list[dict],
) -> tuple[date | None, str | None]:
    """Find the date + name when stock was renamed to '退市...' or '*ST...'.

    Returns (delist_date, new_name) or (None, None) if no delist evidence.
    """
    for entry in history_names:
        name = entry.get("name", "")
        if "退市" in name or name.startswith("*ST"):
            date_str = entry.get("date")
            if not date_str:
                continue
            try:
                return datetime.strptime(date_str, "%Y-%m-%d").date(), name
            except ValueError:
                continue
    return None, None
