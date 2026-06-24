"""Stock-list sync helpers extracted from routers/stocks.py.

Owns the Lixinger → stocks table sync. The router handler stays thin;
this module owns the Lixinger-specific HTTP shape, parsing, and upsert
so the workflow is testable without spinning up FastAPI.
"""

from __future__ import annotations

import logging
from datetime import date as date_type
from typing import TYPE_CHECKING, Optional

from sqlalchemy.orm import Session

from app.models.stock import Stock
from app.schemas.stock import SyncResult
from app.services.lixinger_client import get_lixinger_client

if TYPE_CHECKING:
    from app.services.lixinger_client import LixingerClient

logger = logging.getLogger(__name__)


def _parse_ipo_date(raw) -> Optional[date_type]:
    """Parse Lixinger ipoDate into a date; return None on any parse failure.

    Lixinger returns YYYY-MM-DD (sometimes with trailing time). We tolerate
    a few shapes but never raise — bad dates shouldn't abort the whole sync.
    """
    if not raw:
        return None
    s = str(raw)[:10]
    try:
        parts = s.split("-")
        return date_type(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        return None


def sync_stocks_from_lixinger(db: Session, client: "Optional[LixingerClient]" = None) -> SyncResult:
    """Sync all A-share stocks from Lixinger into the local database.

    Two-phase sync:
    1. Fetch the full company list (auto-paginated past Lixinger's silent
       500-record cap via ``get_company_list_all``) and upsert into stocks.
       Populates ``listing_status`` / ``exchange`` / ``fs_table_type`` /
       ``ipo_date`` (raw Lixinger trading-status fields).
    2. Fetch SW 2021 industry classifications and update the ``industry``
       field. Failures here are logged and skipped — phase 1 still commits.

    Args:
        db: SQLAlchemy session. Caller is responsible for commit/rollback
            lifecycle; this function commits once after phase 1 and once
            after phase 2.
        client: Optional pre-constructed LixingerClient (dependency injection
            for tests). If None, the module-level singleton is used.

    Returns:
        SyncResult with counts for total_fetched / inserted / updated /
        skipped / industry_updated.
    """
    if client is None:
        client = get_lixinger_client()

    # ── Phase 1: Company list (auto-paginating) ─────────────────────────
    all_companies: list[dict] = client.get_company_list_all()

    existing_codes = {code for (code,) in db.query(Stock.code).all()}
    existing_cache: dict[str, Stock] = {}

    inserted = 0
    updated = 0
    skipped = 0

    for c in all_companies:
        code = (c.get("stockCode") or "").strip()
        if not code:
            skipped += 1
            continue

        name = (c.get("name") or "").strip()
        listing_status = c.get("listingStatus")
        exchange = c.get("exchange")
        fs_table_type = c.get("fsTableType")
        ipo_date = _parse_ipo_date(c.get("ipoDate"))
        # Listed_date (legacy) — keep populating from the same source for
        # backwards compat with existing screens that filter on it.
        listed_date = ipo_date or _parse_listed_date_legacy(c)

        if code in existing_codes:
            stock = existing_cache.get(code)
            if stock is None:
                stock = db.query(Stock).filter(Stock.code == code).first()
                if stock is not None:
                    existing_cache[code] = stock
            changed = False
            if stock is not None:
                if name and stock.name != name:
                    stock.name = name
                    changed = True
                if listing_status and stock.listing_status != listing_status:
                    stock.listing_status = listing_status
                    changed = True
                if exchange and stock.exchange != exchange:
                    stock.exchange = exchange
                    changed = True
                if fs_table_type and stock.fs_table_type != fs_table_type:
                    stock.fs_table_type = fs_table_type
                    changed = True
                if ipo_date and stock.ipo_date != ipo_date:
                    stock.ipo_date = ipo_date
                    changed = True
                if listed_date and stock.listed_date != listed_date:
                    stock.listed_date = listed_date
                    changed = True
            if changed:
                updated += 1
            else:
                skipped += 1
        else:
            db.add(
                Stock(
                    code=code,
                    name=name or code,
                    listing_status=listing_status,
                    exchange=exchange,
                    fs_table_type=fs_table_type,
                    ipo_date=ipo_date,
                    listed_date=listed_date,
                )
            )
            existing_codes.add(code)
            inserted += 1

    db.commit()
    logger.info(
        "Phase 1 complete: fetched=%d, inserted=%d, updated=%d, skipped=%d",
        len(all_companies), inserted, updated, skipped,
    )

    # ── Phase 2: Industry classification (best-effort) ──────────────────
    industry_updated = 0
    try:
        industries = client.get_industry_list(source="sw_2021")
        level1 = [i for i in industries if i.get("level") == "one"]
        level1_codes = [i["stockCode"] for i in level1]
        level1_name_map = {i["stockCode"]: i["name"] for i in level1}

        stock_industry_map = fetch_industry_constituents(
            level1_codes, level1_name_map, client
        )
        logger.info("Fetched industry mapping for %d stocks", len(stock_industry_map))

        for stock_code, industry_name in stock_industry_map.items():
            stock = existing_cache.get(stock_code)
            if stock is None:
                stock = db.query(Stock).filter(Stock.code == stock_code).first()
            if stock and stock.industry != industry_name:
                stock.industry = industry_name
                industry_updated += 1

        db.commit()
    except Exception:
        logger.exception("Industry sync failed, continuing without industry data")

    # v2: Phase 3 (business_pattern inference) removed — concept dropped.

    result = SyncResult(
        total_fetched=len(all_companies),
        inserted=inserted,
        updated=updated,
        skipped=skipped,
        industry_updated=industry_updated,
    )
    logger.info("Stock sync complete: %s", result)
    return result


def _parse_listed_date_legacy(raw) -> Optional[date_type]:
    """Fallback parser for legacy listed_date sources (listingDate / listDate).

    Kept separate from _parse_ipo_date so that if Lixinger ever exposes
    distinct IPO vs listing timestamps, the divergence point is obvious.
    """
    if not raw:
        return None
    s = str(raw)[:10]
    try:
        parts = s.split("-")
        return date_type(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        return None


def fetch_industry_constituents(
    industry_codes: list[str],
    industry_name_map: dict[str, str],
    client: LixingerClient,
) -> dict[str, str]:
    """Fetch stock-to-industry mapping from Lixinger industry constituents API.

    Args:
        industry_codes: Level-1 SW 2021 industry codes.
        industry_name_map: {industry_code: industry_name} from industry list.
        client: LixingerClient instance (uses internal _post with token).

    Returns {stock_code: industry_name}. Batches at 100 codes per request
    (Lixinger's documented limit); per-batch failures are logged and skipped
    so partial results still flow through.
    """
    stock_industry_map: dict[str, str] = {}

    for i in range(0, len(industry_codes), 100):
        batch_codes = industry_codes[i : i + 100]
        try:
            result = client._post(
                "/cn/industry/constituents/sw_2021",
                {"stockCodes": batch_codes, "date": "latest"},
            )
            if not result:
                continue

            for item in result if isinstance(result, list) else result.get("data", []):
                ind_code = item.get("stockCode", "")
                ind_name = industry_name_map.get(ind_code, "")
                for c in item.get("constituents", []):
                    sc = c.get("stockCode", "")
                    if sc and ind_name:
                        stock_industry_map[sc] = ind_name
        except Exception:
            logger.exception(
                "Failed to fetch constituents for batch %d-%d", i, i + 100
            )

    return stock_industry_map
