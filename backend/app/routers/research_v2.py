"""Research API — v2 LLM Pipeline endpoints.

Exposes:
  POST /api/research/{stock_code}              trigger deep_research
  GET  /api/research/{stock_code}/latest       latest report
  GET  /api/research/{stock_code}/history      all reports for stock
  GET  /api/research/reports                   recent reports across stocks
  GET  /api/research/health                    pipeline health (cost, conflicts)

Security notes (per decision 1: single-user, no auth):
  - MISSING_AUTHORIZATION / DATA_ENUMERATION / CACHE_BYPASS: by design
    (v2 is personal single-user system; ADR-008 in v1 also covers this)
  - Rate limiting + budget pre-check on trigger_research prevents accidental
    spend runaway
  - Generic error messages on failure (no exception detail leak)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

import app.db.session as _session_module
from app.core.datetime_utils import now
from app.db.session import get_db
from app.models.research_report import (
    PIPELINE_DEEP_RESEARCH,
    STATUS_FAILED,
    STATUS_RUNNING,
    TERMINAL_STATUSES,
    ResearchReport,
)
from app.models.stock import Stock
from app.services import lifecycle_service
from app.services.llm.cost_tracker import check_budget_available, get_monthly_spend
from app.services.pipelines.llm import deep_research_pipeline
from app.core.rate_limit import limiter

# A "running" placeholder older than this is treated as abandoned (crashed
# server / lost worker) and a fresh run is allowed to supersede it.
RUNNING_STALE_AFTER = timedelta(minutes=15)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/research", tags=["research"])

# Per-decision 9: $150/month hard cap. Pre-check before expensive Pipeline.
# Rate limit: max 10 trigger calls/min (defense against accidental loops).
TRIGGER_RATE_LIMIT = "10/minute"


# ── Schemas ───────────────────────────────────────────────────────────────


class ResearchTriggerRequest(BaseModel):
    force: bool = False  # bypass 30-day cache
    model_tier: str = "sonnet"  # sonnet | opus | haiku
    use_web_search: bool = True
    # trading-philosophy.md §3: sourcing engine selects the scoring profile.
    source: str = "quality_screen"  # quality_screen | theme_scan
    # serenity 卡点 score handed in when source=theme_scan (§3 reuse).
    scarcity_score: float | None = None
    # serenity 失败条件 from theme_scan; folded into 芒格 failure_scenarios (§4.3).
    failure_conditions: list[str] | None = None


class ResearchReportSummary(BaseModel):
    id: int
    stock_code: str
    stock_name: str | None
    pipeline_type: str
    overall_score: float | None
    recommendation: str | None
    evidence_grade: str | None
    status: str
    created_at: datetime | None
    expires_at: datetime | None


class ResearchReportFull(ResearchReportSummary):
    markdown_output: str | None
    data_conflict: list[dict] | None
    red_line_hit: list[dict] | None
    prompt_version: str | None


# ── Endpoints ────────────────────────────────────────────────────────────


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    """Pipeline health: monthly spend + lifecycle counts."""
    spend = get_monthly_spend(db)
    counts = lifecycle_service.count_by_state(db)
    return {
        "spend": spend,
        "lifecycle_counts": counts,
    }

class QualityScreenTriggerResponse(BaseModel):
    """Response from triggering a quality screen."""
    triggered: bool
    message: str


@router.post("/quality-screen", response_model=QualityScreenTriggerResponse)
def trigger_quality_screen(
    db: Session = Depends(get_db),
) -> dict:
    """Trigger a quality_screen pipeline run on the full universe."""
    from app.services.pipelines.llm import quality_screen_pipeline

    try:
        summary = quality_screen_pipeline.screen_universe(db, limit=200)
        db.commit()
        return QualityScreenTriggerResponse(
            triggered=True,
            message=f"Quality screen completed: {summary}"
        )
    except Exception as exc:
        db.rollback()
        logger.exception("Manual quality_screen failed")
        raise HTTPException(status_code=500, detail=str(exc))



class BatchResearchRequest(BaseModel):
    stock_codes: list[str]
    source: str = "quality_screen"
    model_tier: str = "sonnet"
    use_web_search: bool = True
    scarcity_score: float | None = None
    failure_conditions: list[str] | None = None


@router.post("/batch", status_code=202)
def trigger_batch_research(
    request: Request,
    payload: BatchResearchRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Batch-trigger deep_research for multiple stocks.

    Returns 202 immediately. Each stock spawns its own background task.
    Already-running or recently-researched stocks are skipped per existing
    concurrency guard + 30-day cache rules in trigger_research.

    Intended for the Engine page: after theme_scan or quality_screen produces
    candidates, a single click submits them all for deep research.
    """
    allowed, reason = check_budget_available(db)
    if not allowed:
        raise HTTPException(429, f"LLM budget exhausted: {reason}")

    triggered: list[str] = []
    skipped: list[dict] = []

    for code in payload.stock_codes:
        stock = db.query(Stock).filter(Stock.code == code).first()
        if stock is None:
            skipped.append({"code": code, "reason": "not_found"})
            continue

        # Check in-flight
        if _get_running_report(db, code) is not None:
            skipped.append({"code": code, "reason": "already_running"})
            continue

        # Check 30-day cache
        if not lifecycle_service.needs_research(
            db, code, cache_days=30
        ):
            skipped.append({"code": code, "reason": "cache_valid"})
            continue

        # Create placeholder row
        placeholder = ResearchReport(
            stock_code=code,
            pipeline_type=PIPELINE_DEEP_RESEARCH,
            status=STATUS_RUNNING,
        )
        db.add(placeholder)
        db.flush()
        db.refresh(placeholder)

        _try_trigger_task(
            db=db,
            stock_code=code,
            report_id=placeholder.id,
            source=payload.source,
            scarcity_score=payload.scarcity_score,
            failure_conditions=payload.failure_conditions,
            model_tier=payload.model_tier,
            use_web_search=payload.use_web_search,
        )
        triggered.append(code)

    db.commit()
    return {
        "triggered": triggered,
        "triggered_count": len(triggered),
        "skipped": skipped,
        "skipped_count": len(skipped),
    }


@router.post("/{stock_code}", response_model=ResearchReportFull, status_code=202)
@limiter.limit(TRIGGER_RATE_LIMIT)
def trigger_research(
    request: Request,
    stock_code: str,
    response: Response,
    payload: ResearchTriggerRequest | None = None,
    db: Session = Depends(get_db),
) -> ResearchReportFull:
    """Trigger deep_research_pipeline for a stock (asynchronous).

    deep_research is a multi-minute LLM job, so it runs in the background:
    this returns 202 immediately with a "running" placeholder report whose
    ``status`` flips to a terminal value when the job finishes. The client
    polls GET /{stock_code}/latest to observe completion.

    Skips (returns 200 + existing report) if research within 30 days, unless
    force=True. Pre-checks monthly budget. Rate-limited to 10/min.
    """
    payload = payload or ResearchTriggerRequest()

    # Check stock exists
    stock = db.query(Stock).filter(Stock.code == stock_code).first()
    if stock is None:
        raise HTTPException(404, f"Stock not found: {stock_code}")

    # Budget pre-check (per decision 9: hard cap $150)
    allowed, reason = check_budget_available(db)
    if not allowed:
        raise HTTPException(429, f"LLM budget exhausted: {reason}")

    # Concurrency guard: a fresh "running" placeholder means a job is already
    # in flight for this stock — return it instead of launching a duplicate
    # (which would double-spend the LLM budget).
    in_flight = _get_running_report(db, stock_code)
    if in_flight is not None:
        response.status_code = 202
        return _to_full_response(in_flight)

    # 30-day cache check (unless force)
    if not payload.force and not lifecycle_service.needs_research(db, stock_code, cache_days=30):
        latest = _get_latest_report(db, stock_code)
        if latest:
            response.status_code = 200
            return _to_full_response(latest)

    # Create the "running" placeholder row up front so the client gets an id
    # to poll while the background job runs.
    placeholder = ResearchReport(
        stock_code=stock_code,
        pipeline_type=PIPELINE_DEEP_RESEARCH,
        status=STATUS_RUNNING,
    )
    db.add(placeholder)
    db.commit()
    db.refresh(placeholder)

    _try_trigger_task(
        db=db,
        stock_code=stock_code,
        report_id=placeholder.id,
        source=payload.source,
        scarcity_score=payload.scarcity_score,
        failure_conditions=payload.failure_conditions,
        model_tier=payload.model_tier,
        use_web_search=payload.use_web_search,
    )

    response.status_code = 202
    return _to_full_response(placeholder)



def _mark_report_failed(db: Session, report_id: int) -> None:
    """Best-effort: flip the placeholder to FAILED in its own transaction."""
    try:
        report = db.query(ResearchReport).filter(
            ResearchReport.id == report_id
        ).first()
        if report is not None:
            report.status = STATUS_FAILED
            report.markdown_output = "深度研究失败，请查看服务端日志。"
            db.commit()
    except Exception:
        db.rollback()
        logger.exception("failed to mark report %s as FAILED", report_id)


@router.get("/{stock_code}/latest", response_model=ResearchReportFull | None)
def get_latest(stock_code: str, db: Session = Depends(get_db)) -> ResearchReportFull | None:
    """Get latest research report for a stock."""
    report = _get_latest_report(db, stock_code)
    if report is None:
        return None
    return _to_full_response(report)


@router.get("/{stock_code}/history", response_model=list[ResearchReportSummary])
def get_history(
    stock_code: str,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[ResearchReportSummary]:
    """All reports for a stock (newest first)."""
    stock = db.query(Stock.name).filter(Stock.code == stock_code).first()
    stock_name = stock[0] if stock else None
    rows = (
        db.query(ResearchReport)
        .filter(ResearchReport.stock_code == stock_code)
        .order_by(desc(ResearchReport.created_at))
        .limit(limit)
        .all()
    )
    return [_to_summary(r, stock_name) for r in rows]


@router.get("/reports", response_model=list[ResearchReportSummary])
def list_recent_reports(
    pipeline_type: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[ResearchReportSummary]:
    """Recent reports across all stocks (latest per stock + pipeline_type, deduped)."""
    # Subquery: latest report id per (stock_code, pipeline_type)
    subq_base = db.query(
        ResearchReport.stock_code,
        ResearchReport.pipeline_type,
        func.max(ResearchReport.id).label('max_id'),
    )
    if pipeline_type:
        subq_base = subq_base.filter(ResearchReport.pipeline_type == pipeline_type)
    subq = subq_base.group_by(
        ResearchReport.stock_code, ResearchReport.pipeline_type
    ).subquery()

    q = (
        db.query(ResearchReport, Stock.name)
        .join(subq, ResearchReport.id == subq.c.max_id)
        .join(Stock, ResearchReport.stock_code == Stock.code)
    )
    if pipeline_type:
        q = q.filter(ResearchReport.pipeline_type == pipeline_type)
    rows = q.order_by(desc(ResearchReport.created_at)).limit(limit).all()

    return [
        ResearchReportSummary(
            id=r.id,
            stock_code=r.stock_code,
            stock_name=name,
            pipeline_type=r.pipeline_type,
            overall_score=r.overall_score,
            recommendation=r.recommendation,
            evidence_grade=r.evidence_grade,
            status=r.status,
            created_at=r.created_at,
            expires_at=r.expires_at,
        )
        for r, name in rows
    ]


# ── Helpers ──────────────────────────────────────────────────────────────


def _get_latest_report(db: Session, stock_code: str) -> ResearchReport | None:
    return (
        db.query(ResearchReport)
        .filter(ResearchReport.stock_code == stock_code)
        .order_by(desc(ResearchReport.created_at))
        .first()
    )


def _get_running_report(db: Session, stock_code: str) -> ResearchReport | None:
    """Most recent non-stale "running" placeholder for a stock, if any.

    A placeholder older than RUNNING_STALE_AFTER is treated as abandoned and
    ignored, so a crashed job can't block new runs forever.
    """
    cutoff = now() - RUNNING_STALE_AFTER
    return (
        db.query(ResearchReport)
        .filter(
            ResearchReport.stock_code == stock_code,
            ResearchReport.status == STATUS_RUNNING,
            ResearchReport.created_at >= cutoff,
        )
        .order_by(desc(ResearchReport.created_at))
        .first()
    )


def _to_summary(r: ResearchReport, stock_name: str | None = None) -> ResearchReportSummary:
    return ResearchReportSummary(
        id=r.id,
        stock_code=r.stock_code,
        stock_name=stock_name,
        pipeline_type=r.pipeline_type,
        overall_score=r.overall_score,
        recommendation=r.recommendation,
        evidence_grade=r.evidence_grade,
        status=r.status,
        created_at=r.created_at,
        expires_at=r.expires_at,
    )


def _to_full_response(r: ResearchReport) -> ResearchReportFull:
    base = _to_summary(r)
    return ResearchReportFull(
        **base.model_dump(),
        markdown_output=r.markdown_output,
        data_conflict=r.data_conflict_json,
        red_line_hit=r.red_line_hit_json,
        prompt_version=r.prompt_version,
    )


def _try_trigger_task(
    *,
    db,
    stock_code: str,
    report_id: int,
    source: str,
    scarcity_score: float | None,
    failure_conditions: list[str] | None,
    model_tier: str,
    use_web_search: bool,
) -> None:
    """Try TaskEngine first; fall back to synchronous execution."""
    from app.services.llm.client import GLMTier
    from app.services.pipelines.llm import deep_research_pipeline

    try:
        from app.routers.task import _get_engine as _task_engine
        engine = _task_engine()
        engine.trigger_task(
            "deep_research_on_demand",
            db,
            triggered_by="api",
            input_data={
                "stock_code": stock_code,
                "report_id": report_id,
                "source": source,
                "scarcity_score": scarcity_score,
                "failure_conditions": failure_conditions,
                "model_tier": model_tier,
                "use_web_search": use_web_search,
            },
        )
        return  # TaskEngine will handle execution
    except Exception:
        logger.warning("TaskEngine unavailable, running synchronously for %s", stock_code)

    # Fallback: synchronous execution (for tests / engine-not-ready scenarios)
    tier_map = {"sonnet": GLMTier.SONNET, "opus": GLMTier.OPUS, "haiku": GLMTier.HAIKU}
    tier = tier_map.get(model_tier.lower(), GLMTier.SONNET)

    try:
        deep_research_pipeline.run(
            stock_code,
            source=source,
            scarcity_score=scarcity_score,
            failure_conditions=failure_conditions,
            model_tier=tier,
            use_web_search=use_web_search,
            db_session=db,
            existing_report_id=report_id,
        )
    except Exception:
        logger.exception("Fallback research failed for %s", stock_code)
        _mark_report_failed(db, report_id)
