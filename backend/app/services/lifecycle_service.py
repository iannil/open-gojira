"""Stock lifecycle state machine.

Per decision 7-9 (redesign-decisions-v2.md): tracks each stock's position
in the funnel:
  universe → watchlist → researched → candidate → signaled → holding → exited

Each transition is recorded in `history_json` for audit trail.
`last_research_at` enables 30-day re-research cache (decision 8).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.datetime_utils import now
from app.models.stock_lifecycle import (
    ALL_STATES,
    STATE_CANDIDATE,
    STATE_EXITED,
    STATE_HOLDING,
    STATE_RESEARCHED,
    STATE_SIGNALED,
    STATE_UNIVERSE,
    STATE_WATCHLIST,
    StockLifecycle,
)

logger = logging.getLogger(__name__)


# Allowed transitions (forward + a few backward).
# v2 reality: stocks can be researched directly from universe (manual trigger
# via CLI/API), so universe allows direct jumps to any post-research state.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    STATE_UNIVERSE: {STATE_WATCHLIST, STATE_RESEARCHED, STATE_CANDIDATE, STATE_HOLDING},
    STATE_WATCHLIST: {STATE_RESEARCHED, STATE_CANDIDATE, STATE_UNIVERSE},
    STATE_RESEARCHED: {STATE_CANDIDATE, STATE_WATCHLIST, STATE_HOLDING, STATE_SIGNALED},
    STATE_CANDIDATE: {STATE_SIGNALED, STATE_RESEARCHED, STATE_HOLDING},
    STATE_SIGNALED: {STATE_HOLDING, STATE_CANDIDATE},
    STATE_HOLDING: {STATE_EXITED},
    STATE_EXITED: {STATE_WATCHLIST, STATE_RESEARCHED},  # re-research later
}


class InvalidTransitionError(Exception):
    pass


def get_lifecycle(db: Session, stock_code: str) -> Optional[StockLifecycle]:
    """Get lifecycle record; None if stock not yet tracked."""
    return db.query(StockLifecycle).filter(
        StockLifecycle.stock_code == stock_code
    ).first()


def get_state(db: Session, stock_code: str) -> str:
    """Get current state; STATE_UNIVERSE if not yet tracked."""
    lc = get_lifecycle(db, stock_code)
    return lc.current_state if lc else STATE_UNIVERSE


def enter_state(
    db: Session,
    stock_code: str,
    new_state: str,
    *,
    reason: str = "",
    metadata: Optional[dict[str, Any]] = None,
    allow_backwards: bool = False,
    bump_research_at: bool = False,
) -> StockLifecycle:
    """Transition a stock to a new state.

    Args:
        db: session
        stock_code: stock code
        new_state: target state (must be in ALL_STATES)
        reason: human-readable reason for audit
        metadata: optional dict stored in history entry
        allow_backwards: if True, skip transition validation (force)
        bump_research_at: if True, set last_research_at = now (for researched
            state) — used for 30-day cache window

    Returns:
        Updated StockLifecycle record.

    Raises:
        InvalidTransitionError if transition not in ALLOWED_TRANSITIONS
            and allow_backwards is False.
        ValueError if new_state is not a known state.
    """
    if new_state not in ALL_STATES:
        raise ValueError(f"Unknown state: {new_state}. Expected one of {ALL_STATES}")

    lc = get_lifecycle(db, stock_code)
    current = lc.current_state if lc else STATE_UNIVERSE

    if current != new_state:
        if not allow_backwards:
            allowed = ALLOWED_TRANSITIONS.get(current, set())
            if new_state not in allowed:
                raise InvalidTransitionError(
                    f"Cannot transition {stock_code} from '{current}' to '{new_state}'. "
                    f"Allowed: {allowed}"
                )

        ts = now()
        history_entry = {
            "from": current,
            "to": new_state,
            "at": ts.isoformat(),
            "reason": reason,
            "metadata": metadata or {},
        }

        if lc is None:
            lc = StockLifecycle(
                stock_code=stock_code,
                current_state=new_state,
                entered_state_at=ts,
                last_research_at=ts if (bump_research_at or new_state == STATE_RESEARCHED) else None,
                rejected_count=0,
                history_json=[history_entry],
            )
            db.add(lc)
        else:
            lc.current_state = new_state
            lc.entered_state_at = ts
            if bump_research_at or new_state == STATE_RESEARCHED:
                lc.last_research_at = ts
            history = lc.history_json or []
            history.append(history_entry)
            lc.history_json = history

        db.flush()
        logger.info(
            "lifecycle_transition: %s %s → %s (reason=%s)",
            stock_code, current, new_state, reason or "n/a",
        )

    return lc  # type: ignore[return-value]


def mark_researched(
    db: Session,
    stock_code: str,
    *,
    rejected: bool = False,
    reason: str = "",
    promote_to_candidate: bool = False,
) -> StockLifecycle:
    """Mark a stock as researched (after deep_research_pipeline runs).

    Updates last_research_at (for 30-day cache). If rejected=True (mirror test
    failed or red line hit), increments rejected_count but still moves to
    researched state (so we don't re-research too often).

    If promote_to_candidate=True and not rejected, transitions directly to
    candidate state (skipping intermediate researched) — see trading-philosophy
    §2: a successful deep_research promotes the stock to candidate pool.
    """
    target = STATE_CANDIDATE if (promote_to_candidate and not rejected) else STATE_RESEARCHED
    lc = enter_state(
        db, stock_code, target,
        reason=reason or ("rejected" if rejected else f"research completed → {target}"),
        bump_research_at=True,
    )
    if rejected:
        lc.rejected_count = (lc.rejected_count or 0) + 1
        db.flush()
    return lc


def needs_research(
    db: Session,
    stock_code: str,
    *,
    cache_days: int = 30,
) -> bool:
    """Check if stock needs new research (per decision 8: 30-day cache).

    Returns True if:
      - Never researched (last_research_at is None)
      - Last research older than cache_days
    """
    lc = get_lifecycle(db, stock_code)
    if lc is None or lc.last_research_at is None:
        return True
    age = now() - lc.last_research_at
    return age.days >= cache_days


def get_by_state(
    db: Session,
    states: str | list[str] | None = None,
    *,
    limit: int = 200,
) -> list[StockLifecycle]:
    """List lifecycle records filtered by state(s).

    Args:
        states: single state, list of states, or None (all).
        limit: max rows to return (default 200).

    Returns:
        List of StockLifecycle records, ordered by entered_state_at desc.
    """
    q = db.query(StockLifecycle)
    if states is not None:
        if isinstance(states, str):
            states = [states]
        q = q.filter(StockLifecycle.current_state.in_(states))
    q = q.order_by(StockLifecycle.entered_state_at.desc()).limit(limit)
    return q.all()


def count_by_state(db: Session) -> dict[str, int]:
    """Counts per state — for dashboard / health metrics."""
    from sqlalchemy import func
    rows = db.query(
        StockLifecycle.current_state,
        func.count(StockLifecycle.stock_code),
    ).group_by(StockLifecycle.current_state).all()
    counts = {state: 0 for state in ALL_STATES}
    for state, cnt in rows:
        counts[state] = cnt
    return counts
