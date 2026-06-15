"""Export ranked companies to Watchlist.

Implements Q3 D / Q11: no DisciplineChecklistModal here (it triggers
later when a Watchlist item flows into a Draft).

Phase 1 limitation: only `target="watchlist"` supported. Candidate
export requires schema change (add `source` column, loosen plan_id
FK), deferred to Phase 2 per Q3 discussion.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.research_company_ranking import ResearchCompanyRanking
from app.models.research_run import ResearchRun
from app.models.watchlist import WatchlistItem
from app.services.research_runner_service import ResearchRunnerError

logger = logging.getLogger(__name__)


def export_ranking(
    db: Session,
    run_id: int,
    target: str,  # "watchlist" (Phase 1 only)
    rank_max: int = 3,
    watchlist_group_id: int | None = None,
) -> dict:
    """Export Top N ranked companies from a run to a Watchlist group.

    Returns {"exported_count", "skipped_codes", "target", "target_id"}.
    """
    if target != "watchlist":
        raise ResearchRunnerError(
            f"target='{target}' not supported in Phase 1 (only 'watchlist'). "
            f"Candidate export deferred to Phase 2 (needs Candidate.source column)."
        )
    if rank_max < 1 or rank_max > 7:
        raise ResearchRunnerError(f"rank_max must be 1-7, got {rank_max}")
    if watchlist_group_id is None:
        raise ResearchRunnerError(
            "watchlist_group_id is required when target='watchlist'"
        )

    run = db.query(ResearchRun).filter(ResearchRun.id == run_id).first()
    if not run:
        raise ResearchRunnerError(f"ResearchRun id={run_id} not found")
    if run.status != "completed":
        raise ResearchRunnerError(
            f"ResearchRun id={run_id} status={run.status}, must be 'completed'"
        )

    rankings = (
        db.query(ResearchCompanyRanking)
        .filter(ResearchCompanyRanking.research_run_id == run_id)
        .filter(ResearchCompanyRanking.rank <= rank_max)
        .order_by(ResearchCompanyRanking.rank)
        .all()
    )

    exported = 0
    skipped: list[str] = []
    for r in rankings:
        try:
            _export_to_watchlist(db, watchlist_group_id, r, run_id)
            exported += 1
        except _SkipExport as exc:
            skipped.append(f"{r.stock_code} ({exc})")

    db.commit()
    return {
        "exported_count": exported,
        "skipped_codes": skipped,
        "target": target,
        "target_id": watchlist_group_id,
    }


class _SkipExport(Exception):
    """Internal: skip this stock without aborting the batch."""


def _export_to_watchlist(
    db: Session, group_id: int, ranking: ResearchCompanyRanking, run_id: int
) -> None:
    existing = (
        db.query(WatchlistItem)
        .filter(
            WatchlistItem.group_id == group_id,
            WatchlistItem.stock_code == ranking.stock_code,
        )
        .first()
    )
    if existing:
        raise _SkipExport("already in watchlist group")
    item = WatchlistItem(
        group_id=group_id,
        stock_code=ranking.stock_code,
        note=(
            f"serenity run #{run_id} rank={ranking.rank}: "
            f"{ranking.constrains_what}"
        ),
    )
    db.add(item)
