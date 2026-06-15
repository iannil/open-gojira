"""Export ranked companies to Watchlist or Candidate.

Q3 D: distinct source tagging (rule_based vs serenity).
Q11: no DisciplineChecklistModal here.

Serenity-exported Candidates have no user Plan, so they are written with
plan_id=NULL (made nullable by s2_candidate_source_field migration).
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.candidate import Candidate
from app.models.research_company_ranking import ResearchCompanyRanking
from app.models.research_run import ResearchRun
from app.models.watchlist import WatchlistItem
from app.services.research_runner_service import ResearchRunnerError

logger = logging.getLogger(__name__)


def export_ranking(
    db: Session,
    run_id: int,
    target: str,  # "watchlist" | "candidate"
    rank_max: int = 3,
    watchlist_group_id: int | None = None,
) -> dict:
    """Export Top N ranked companies from a run.

    Returns {"exported_count", "skipped_codes", "target", "target_id"}.
    """
    if target not in ("watchlist", "candidate"):
        raise ResearchRunnerError(f"invalid target: {target}")
    if rank_max < 1 or rank_max > 7:
        raise ResearchRunnerError(f"rank_max must be 1-7, got {rank_max}")
    if target == "watchlist" and watchlist_group_id is None:
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
            if target == "watchlist":
                _export_to_watchlist(db, watchlist_group_id, r, run_id)
            else:
                _export_to_candidate(db, r, run_id)
            exported += 1
        except _SkipExport as exc:
            skipped.append(f"{r.stock_code} ({exc})")

    db.commit()
    return {
        "exported_count": exported,
        "skipped_codes": skipped,
        "target": target,
        "target_id": watchlist_group_id if target == "watchlist" else None,
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


def _export_to_candidate(
    db: Session,
    ranking: ResearchCompanyRanking,
    run_id: int,
) -> None:
    """Write to candidates with source='serenity', plan_id=NULL.

    Q3 D: distinct from rule_based candidates (audit/draft_matcher can filter).
    Q11: no DisciplineChecklistModal at export time.
    """
    existing = (
        db.query(Candidate)
        .filter(
            Candidate.stock_code == ranking.stock_code,
            Candidate.source == "serenity",
            Candidate.status == "active",
        )
        .first()
    )
    if existing:
        raise _SkipExport("already an active serenity candidate")

    db.add(Candidate(
        plan_id=None,  # serenity Candidates have no user Plan
        stock_code=ranking.stock_code,
        status="active",
        source="serenity",
        pinned=False,  # user can pin later if they want to keep
        notes=(
            f"serenity run #{run_id} rank={ranking.rank}: "
            f"{ranking.constrains_what} | risk: {ranking.main_risk_md[:200]}"
        ),
    ))
