"""Intraday monitor — periodic price poll + risk check orchestration.

Drives the scheduler's intraday_price_poll job (S5.4).

watch_list: union of held + watched + pending-draft + thesis-tracked
stocks. Bounded size (~50-200) to stay within Sina's tolerance.

poll_once():
1. Determine watch_list
2. Batch fetch realtime quotes (one Sina call)
3. For each held position: check_holding (stop loss / take profit)
4. Aggregate events into PollResult
5. (Deferred) check alert_rules for price thresholds
6. (Deferred) refresh pending_drafts if target_price drifted > 5%
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Set

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.candidate import Candidate
from app.models.draft import Draft
from app.models.watchlist import WatchlistItem
from app.services.holding_view_service import get_holding_view
from app.services.realtime_quote_service import get_realtime_prices
from app.services.stop_loss_service import (
    StopLossEvent,
    TakeProfitEvent,
    check_holding,
)


logger = logging.getLogger(__name__)


@dataclass
class PollResult:
    timestamp: datetime
    codes_checked: int
    prices_fetched: int
    stop_loss_events: list = field(default_factory=list)
    take_profit_events: list = field(default_factory=list)
    errors: list = field(default_factory=list)


def intraday_watch_list(db: Session) -> Set[str]:
    """Stocks to monitor during trading hours.

    Union of:
    - open holdings (current positions)
    - active watchlist items
    - pending drafts (target stocks not yet executed)
    - candidates (recent strategy hits)
    """
    codes: Set[str] = set()

    # Open holdings
    for h in get_holding_view(db):
        codes.add(h["stock_code"])

    # Active watchlist
    items = db.execute(select(WatchlistItem.stock_code)).scalars().all()
    codes.update(items)

    # Pending drafts (target stocks not yet executed)
    drafts = db.execute(
        select(Draft.code).where(Draft.status == "pending")
    ).scalars().all()
    codes.update(drafts)

    # Active candidates
    candidates = db.execute(
        select(Candidate.stock_code).distinct()
    ).scalars().all()
    codes.update(candidates)

    # Filter out None / empty
    return {c for c in codes if c}


def poll_once(db: Session) -> PollResult:
    """Single polling cycle. Safe to call from scheduler.

    Steps:
    1. Build watch_list
    2. Batch fetch realtime quotes (one Sina call)
    3. For each held position: check_holding()
    4. Collect events into PollResult
    5. Commit any state changes (peak_price, triggered_at)
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    codes = intraday_watch_list(db)
    result = PollResult(timestamp=now, codes_checked=len(codes), prices_fetched=0)

    if not codes:
        return result

    # Batch fetch (single Sina call)
    code_list = list(codes)
    try:
        quotes = get_realtime_prices(code_list)
        result.prices_fetched = len(quotes)
    except Exception as e:
        logger.error("Realtime fetch failed: %s", e)
        result.errors.append(f"realtime_fetch: {e}")
        return result

    # Check stop loss / take profit for held positions only
    holdings = {h["stock_code"]: h for h in get_holding_view(db)}
    for code, quote in quotes.items():
        if code not in holdings:
            continue
        current_price = quote.get("current", 0)
        if current_price <= 0:
            continue
        try:
            event = check_holding(db, code, current_price)
            if event:
                if isinstance(event, StopLossEvent):
                    result.stop_loss_events.append(event)
                else:
                    result.take_profit_events.append(event)
        except Exception as e:
            logger.error("check_holding failed for %s: %s", code, e)
            result.errors.append(f"{code}: {e}")

    # (Deferred) check alert_rules — would call alert_service.evaluate
    # (Deferred) refresh pending_drafts if target_price drifted

    db.commit()
    return result
