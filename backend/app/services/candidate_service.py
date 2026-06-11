"""Candidate service — CRUD + promote to watchlist."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.candidate import Candidate
from app.models.watchlist import WatchlistGroup, WatchlistItem


def list_all(
    db: Session,
    *,
    plan_id: int | None = None,
    status: str | None = None,
) -> list[Candidate]:
    stmt = select(Candidate)
    if plan_id is not None:
        stmt = stmt.where(Candidate.plan_id == plan_id)
    if status is not None:
        stmt = stmt.where(Candidate.status == status)
    return list(db.execute(stmt.order_by(Candidate.last_confirmed_at.desc())).scalars().all())


def list_for_plan(db: Session, plan_id: int, *, status: str = "active") -> list[Candidate]:
    return list(db.execute(
        select(Candidate).where(
            Candidate.plan_id == plan_id,
            Candidate.status == status,
        ).order_by(Candidate.last_confirmed_at.desc())
    ).scalars().all())


def get_by_id(db: Session, candidate_id: int) -> Candidate | None:
    return db.get(Candidate, candidate_id)


def update(db: Session, candidate: Candidate, *, pinned: bool | None = None, notes: str | None = None) -> Candidate:
    if pinned is not None:
        candidate.pinned = pinned
    if notes is not None:
        candidate.notes = notes
    db.flush()
    return candidate


def promote_to_watchlist(db: Session, candidate: Candidate, group_id: int) -> WatchlistItem:
    """Promote a candidate to a watchlist group."""
    group = db.get(WatchlistGroup, group_id)
    if group is None:
        raise HTTPException(404, f"watchlist group {group_id} not found")

    # Check for duplicate
    existing = db.execute(
        select(WatchlistItem).where(
            WatchlistItem.group_id == group_id,
            WatchlistItem.stock_code == candidate.stock_code,
        )
    ).scalar_one_or_none()

    if existing:
        raise HTTPException(409, f"{candidate.stock_code} already in group {group_id}")

    item = WatchlistItem(
        group_id=group_id,
        stock_code=candidate.stock_code,
        source_candidate_id=candidate.id,
    )
    db.add(item)

    candidate.status = "promoted"
    candidate.removed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.flush()
    return item


def remove(db: Session, candidate: Candidate) -> None:
    candidate.status = "removed"
    candidate.removed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.flush()
