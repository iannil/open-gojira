"""Research endpoints — serenity-skill workflow integration.

Routes:
- GET    /api/research/themes                list research themes
- POST   /api/research/themes                create
- GET    /api/research/themes/{id}           get with latest run summary
- PUT    /api/research/themes/{id}           update
- DELETE /api/research/themes/{id}           archive
- POST   /api/research/themes/{id}/run       trigger run (Q10 async, returns run_id)
- GET    /api/research/themes/{id}/runs      run history
- GET    /api/research/runs/{id}             run details with all children
- POST   /api/research/runs/{id}/export      export Top N (Q11 no Checklist)
- GET    /api/research/appearances/{code}    reverse-link for StockDetail (Q14)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.research_company_ranking import ResearchCompanyRanking
from app.models.research_company_universe import ResearchCompanyUniverse
from app.models.research_evidence import ResearchEvidence
from app.models.research_run import ResearchRun
from app.models.research_theme import ResearchTheme
from app.models.scarce_layer import ScarceLayer
from app.models.value_chain_layer import ValueChainLayer
from app.schemas.common import OkResponse
from app.schemas.research import (
    ResearchExportRequest,
    ResearchExportResponse,
    ResearchRunResponse,
    ResearchRunSummaryResponse,
    ResearchRunTriggerRequest,
    ResearchThemeCreate,
    ResearchThemeResponse,
    ResearchThemeUpdate,
    StockResearchAppearance,
)
from app.services.research_diff_service import RunDiffResponse
from app.services.research_export_service import export_ranking
from app.services.research_runner_service import (
    ResearchRunnerError,
    trigger_run,
)

router = APIRouter(prefix="/api/research", tags=["research"])


# ── CRUD on ResearchTheme ───────────────────────────────────────────────


@router.get("/themes", response_model=list[ResearchThemeResponse])
def list_themes(
    status: str | None = None,
    db: Session = Depends(get_db),
):
    """List all research themes, optionally filter by status."""
    q = db.query(ResearchTheme)
    if status:
        q = q.filter(ResearchTheme.status == status)
    return q.order_by(ResearchTheme.created_at.desc()).all()


@router.post("/themes", response_model=ResearchThemeResponse, status_code=201)
def create_theme(payload: ResearchThemeCreate, db: Session = Depends(get_db)):
    theme = ResearchTheme(
        name=payload.name,
        description=payload.description,
        market=payload.market,
        auto_refresh_freq=payload.auto_refresh_freq,
        parent_theme_id=payload.parent_theme_id,
    )
    db.add(theme)
    db.commit()
    db.refresh(theme)
    return theme


@router.get("/themes/{theme_id}", response_model=ResearchThemeResponse)
def get_theme(theme_id: int, db: Session = Depends(get_db)):
    theme = db.query(ResearchTheme).filter(ResearchTheme.id == theme_id).first()
    if not theme:
        raise HTTPException(404, "ResearchTheme not found")
    return theme


@router.put("/themes/{theme_id}", response_model=ResearchThemeResponse)
def update_theme(
    theme_id: int,
    payload: ResearchThemeUpdate,
    db: Session = Depends(get_db),
):
    theme = db.query(ResearchTheme).filter(ResearchTheme.id == theme_id).first()
    if not theme:
        raise HTTPException(404, "ResearchTheme not found")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(theme, key, value)
    db.commit()
    db.refresh(theme)
    return theme


@router.delete("/themes/{theme_id}", response_model=OkResponse)
def delete_theme(theme_id: int, db: Session = Depends(get_db)):
    theme = db.query(ResearchTheme).filter(ResearchTheme.id == theme_id).first()
    if not theme:
        raise HTTPException(404, "ResearchTheme not found")
    # Soft archive (cascade delete would orphan historical runs)
    theme.status = "archived"
    db.commit()
    return {"ok": True}


# ── Trigger / list runs ─────────────────────────────────────────────────


@router.post(
    "/themes/{theme_id}/run",
    response_model=ResearchRunSummaryResponse,
    status_code=201,
)
def trigger_theme_run(
    theme_id: int,
    payload: ResearchRunTriggerRequest | None = None,
    db: Session = Depends(get_db),
):
    """Q10 async trigger: returns run_id immediately. Caller polls status."""
    payload = payload or ResearchRunTriggerRequest()
    try:
        run = trigger_run(
            db=db,
            theme_id=theme_id,
            triggered_by="manual",
            market=payload.market,
            time_window=payload.time_window,
        )
    except ResearchRunnerError as exc:
        raise HTTPException(409, str(exc)) from exc

    return _summarize_run(run)


@router.get(
    "/themes/{theme_id}/runs",
    response_model=list[ResearchRunSummaryResponse],
)
def list_theme_runs(
    theme_id: int,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    runs = (
        db.query(ResearchRun)
        .filter(ResearchRun.research_theme_id == theme_id)
        .order_by(ResearchRun.started_at.desc())
        .limit(limit)
        .all()
    )
    return [_summarize_run(r) for r in runs]


@router.get("/runs/diff", response_model=RunDiffResponse)
def diff_runs(
    run_a: int,
    run_b: int,
    db: Session = Depends(get_db),
):
    """Phase 2 #10: Compute diff between two completed runs of the same theme.

    Query params: ?run_a=X&run_b=Y (any order; service normalizes by started_at).

    Returns 422 on:
    - run_a or run_b not found (404 if both missing)
    - run_a == run_b
    - runs are different themes
    - either run is not completed

    Per-dimension failures degrade gracefully (dimension set to null +
    flag in `degradations`).

    NOTE: declared BEFORE /runs/{run_id} so "diff" isn't matched as run_id.
    """
    from app.services.research_diff_service import DiffError, compute_diff

    if run_a == run_b:
        raise HTTPException(422, "pick two different runs")

    a = db.query(ResearchRun).filter(ResearchRun.id == run_a).first()
    b = db.query(ResearchRun).filter(ResearchRun.id == run_b).first()
    if not a and not b:
        raise HTTPException(404, f"runs {run_a} and {run_b} not found")
    if not a:
        raise HTTPException(404, f"run {run_a} not found")
    if not b:
        raise HTTPException(404, f"run {run_b} not found")

    if a.research_theme_id != b.research_theme_id:
        raise HTTPException(
            422,
            f"runs must be same theme (run {run_a} theme={a.research_theme_id}, "
            f"run {run_b} theme={b.research_theme_id})",
        )

    if a.status != "completed" or b.status != "completed":
        raise HTTPException(
            422,
            f"both runs must be completed (run {run_a} status={a.status}, "
            f"run {run_b} status={b.status})",
        )

    try:
        return compute_diff(db, run_a, run_b)
    except DiffError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/runs/{run_id}", response_model=ResearchRunResponse)
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.query(ResearchRun).filter(ResearchRun.id == run_id).first()
    if not run:
        raise HTTPException(404, "ResearchRun not found")

    # Load children
    layers = (
        db.query(ValueChainLayer)
        .filter(ValueChainLayer.research_run_id == run_id)
        .order_by(ValueChainLayer.layer_index)
        .all()
    )
    layer_name_by_id = {l.id: l.name for l in layers}

    scarce = (
        db.query(ScarceLayer)
        .filter(ScarceLayer.research_run_id == run_id)
        .order_by(ScarceLayer.rank)
        .all()
    )

    universe = (
        db.query(ResearchCompanyUniverse)
        .filter(ResearchCompanyUniverse.research_run_id == run_id)
        .order_by(ResearchCompanyUniverse.id)
        .all()
    )

    evidence = (
        db.query(ResearchEvidence)
        .filter(ResearchEvidence.research_run_id == run_id)
        .order_by(
            # strong → medium → weak → lead
            ResearchEvidence.grade,
            ResearchEvidence.id,
        )
        .all()
    )

    ranking = (
        db.query(ResearchCompanyRanking)
        .filter(ResearchCompanyRanking.research_run_id == run_id)
        .order_by(ResearchCompanyRanking.rank)
        .all()
    )

    # Build response with joined layer_name
    from app.schemas.research import (
        ResearchCompanyRankingResponse,
        ResearchCompanyUniverseResponse,
        ResearchEvidenceResponse,
        ResearchRunResponse,
        ScarceLayerResponse,
        ValueChainLayerResponse,
    )

    resp = ResearchRunResponse.model_validate(run)
    resp.value_chain_layers = [
        ValueChainLayerResponse.model_validate(l) for l in layers
    ]
    resp.scarce_layers = [
        ScarceLayerResponse.model_validate(
            {**{"id": s.id, "rank": s.rank, "layer_ref_id": s.layer_ref_id,
                "scarcity_reason_md": s.scarcity_reason_md,
                "expansion_difficulty": s.expansion_difficulty,
                "layer_name": layer_name_by_id.get(s.layer_ref_id)},
             **{}}
        )
        for s in scarce
    ]
    resp.company_universe = [
        ResearchCompanyUniverseResponse.model_validate(
            {**{"id": c.id, "stock_code": c.stock_code,
                "classification": c.classification,
                "layer_ref_id": c.layer_ref_id,
                "note": c.note,
                "layer_name": layer_name_by_id.get(c.layer_ref_id) if c.layer_ref_id else None}}
        )
        for c in universe
    ]
    resp.evidence = [
        ResearchEvidenceResponse.model_validate(e) for e in evidence
    ]
    resp.company_ranking = [
        ResearchCompanyRankingResponse.model_validate(r) for r in ranking
    ]
    return resp


@router.post("/runs/{run_id}/export", response_model=ResearchExportResponse)
def export_run(
    run_id: int,
    payload: ResearchExportRequest,
    db: Session = Depends(get_db),
):
    """Export Top N ranked companies. Q11: no DisciplineChecklistModal."""
    try:
        result = export_ranking(
            db=db,
            run_id=run_id,
            target=payload.target,
            rank_max=payload.rank_max,
            watchlist_group_id=payload.watchlist_group_id,
        )
    except ResearchRunnerError as exc:
        raise HTTPException(409, str(exc)) from exc
    return result


# ── Reverse-link (Q14 index-accelerated) ────────────────────────────────


@router.get(
    "/appearances/{stock_code}",
    response_model=list[StockResearchAppearance],
)
def list_appearances(stock_code: str, db: Session = Depends(get_db)):
    """For StockDetail panel: where does this stock appear across research runs?

    Joins research_company_universe + research_company_ranking + research_runs
    + research_themes. Q14: accelerated by index on stock_code columns.
    """
    # Universe rows
    universe_rows = (
        db.query(
            ResearchCompanyUniverse.research_run_id,
            ResearchCompanyUniverse.classification,
        )
        .filter(ResearchCompanyUniverse.stock_code == stock_code)
        .all()
    )
    universe_by_run = {row.research_run_id: row.classification for row in universe_rows}

    # Ranking rows
    ranking_rows = (
        db.query(
            ResearchCompanyRanking.research_run_id,
            ResearchCompanyRanking.rank,
            ResearchCompanyRanking.constrains_what,
            ResearchCompanyRanking.main_risk_md,
        )
        .filter(ResearchCompanyRanking.stock_code == stock_code)
        .all()
    )
    ranking_by_run = {
        row.research_run_id: row for row in ranking_rows
    }

    # Union of run_ids
    all_run_ids = set(universe_by_run) | set(ranking_by_run)
    if not all_run_ids:
        return []

    # Pull run + theme info
    runs = (
        db.query(ResearchRun, ResearchTheme)
        .join(ResearchTheme, ResearchRun.research_theme_id == ResearchTheme.id)
        .filter(ResearchRun.id.in_(all_run_ids))
        .order_by(ResearchRun.started_at.desc())
        .all()
    )

    out = []
    for run, theme in runs:
        rank_info = ranking_by_run.get(run.id)
        out.append(StockResearchAppearance(
            research_theme_id=theme.id,
            research_theme_name=theme.name,
            run_id=run.id,
            run_started_at=run.started_at,
            rank=rank_info.rank if rank_info else None,
            classification=universe_by_run.get(run.id),
            constrains_what=rank_info.constrains_what if rank_info else None,
            main_risk_md=rank_info.main_risk_md if rank_info else None,
        ))
    return out


# ── Helpers ─────────────────────────────────────────────────────────────


def _summarize_run(run: ResearchRun) -> ResearchRunSummaryResponse:
    """Lightweight run view; children counts pulled via separate query when needed."""
    return ResearchRunSummaryResponse(
        id=run.id,
        research_theme_id=run.research_theme_id,
        status=run.status,
        triggered_by=run.triggered_by,
        llm_provider=run.llm_provider,
        llm_token_input=run.llm_token_input,
        llm_token_output=run.llm_token_output,
        llm_search_count=run.llm_search_count,
        started_at=run.started_at,
        completed_at=run.completed_at,
        company_count=0,  # populated by router-level query if needed
        evidence_count=0,
        ranking_count=0,
    )
