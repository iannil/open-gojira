"""Candidate service — CRUD only.

Note (重审 2026-06-13 #1+#4): promote_to_watchlist was removed. Candidates
no longer need a manual "promote" step to trigger trading rule evaluation;
plan_runner now evaluates trading rules for all passing candidates directly.
The watchlist table remains as a manual stock pool (organizational, not gating).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.candidate import Candidate
from app.core.datetime_utils import now


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


def remove(db: Session, candidate: Candidate) -> None:
    candidate.status = "removed"
    candidate.removed_at = now()
    db.flush()
