"""Tests for research export service.

Covers Q3 D (export to Watchlist only in Phase 1) + Q11 (no Checklist).
"""
from __future__ import annotations

import pytest

from app.models.research_company_ranking import ResearchCompanyRanking
from app.models.research_run import ResearchRun
from app.models.research_theme import ResearchTheme
from app.models.stock import Stock
from app.models.watchlist import WatchlistGroup, WatchlistItem
from app.services.research_export_service import export_ranking
from app.services.research_runner_service import ResearchRunnerError


@pytest.fixture
def completed_run_with_ranking(db_session):
    theme = ResearchTheme(name="测试主题", market="A_SHARE")
    db_session.add(theme)
    db_session.flush()

    run = ResearchRun(
        research_theme_id=theme.id, status="completed",
        scope_market="A_SHARE", scope_time_window="3-12M",
        triggered_by="manual", llm_provider="glm-4.7",
    )
    db_session.add(run)
    db_session.flush()

    # 3 ranked stocks
    for rank in range(1, 4):
        code = f"30000{rank}"
        stock = Stock(code=code, name=f"公司{rank}")
        db_session.add(stock)
        db_session.add(ResearchCompanyRanking(
            research_run_id=run.id, rank=rank, stock_code=code,
            constrains_what=f"环节{rank}", chain_position=f"位置{rank}",
            rank_reason_md=f"原因{rank}", evidence_summary_md=f"证据{rank}",
            main_risk_md=f"风险{rank}",
        ))
    db_session.flush()
    return theme, run


def test_export_to_watchlist_success(db_session, completed_run_with_ranking):
    """Q3 D: export Top N to Watchlist."""
    theme, run = completed_run_with_ranking
    group = WatchlistGroup(name="serenity 导出")
    db_session.add(group)
    db_session.flush()

    result = export_ranking(
        db=db_session, run_id=run.id, target="watchlist",
        rank_max=3, watchlist_group_id=group.id,
    )

    assert result["exported_count"] == 3
    assert result["target"] == "watchlist"
    assert result["target_id"] == group.id
    items = db_session.query(WatchlistItem).all()
    assert len(items) == 3
    assert all("serenity run #" in (it.note or "") for it in items)


def test_export_phase1_rejects_candidate_target(db_session, completed_run_with_ranking):
    """Phase 1 limitation: only watchlist supported."""
    _, run = completed_run_with_ranking
    with pytest.raises(ResearchRunnerError, match=r"Phase 1.*watchlist"):
        export_ranking(
            db=db_session, run_id=run.id, target="candidate",
            rank_max=3, watchlist_group_id=None,
        )


def test_export_rejects_running_run(db_session, completed_run_with_ranking):
    """Cannot export from a Run that isn't completed."""
    _, run = completed_run_with_ranking
    run.status = "running"
    db_session.flush()
    with pytest.raises(ResearchRunnerError, match=r"status=running"):
        export_ranking(
            db=db_session, run_id=run.id, target="watchlist",
            rank_max=3, watchlist_group_id=1,
        )


def test_export_skips_already_in_watchlist(db_session, completed_run_with_ranking):
    """Q11: duplicate codes are skipped without aborting the batch."""
    theme, run = completed_run_with_ranking
    group = WatchlistGroup(name="已有")
    db_session.add(group)
    db_session.flush()
    # Pre-seed one of the ranked stocks
    db_session.add(WatchlistItem(
        group_id=group.id, stock_code="300001", note="之前加过",
    ))
    db_session.flush()

    result = export_ranking(
        db=db_session, run_id=run.id, target="watchlist",
        rank_max=3, watchlist_group_id=group.id,
    )

    assert result["exported_count"] == 2  # 300001 was skipped
    assert "300001" in result["skipped_codes"][0]


def test_export_rejects_invalid_rank_max(db_session, completed_run_with_ranking):
    """rank_max must be 1-7."""
    _, run = completed_run_with_ranking
    with pytest.raises(ResearchRunnerError, match=r"1-7"):
        export_ranking(
            db=db_session, run_id=run.id, target="watchlist",
            rank_max=10, watchlist_group_id=1,
        )
