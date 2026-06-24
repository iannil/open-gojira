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
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.research_report import ResearchReport
from app.models.stock import Stock
from app.services import lifecycle_service
from app.services.llm.cost_tracker import check_budget_available, get_monthly_spend
from app.services.pipelines.llm import deep_research_pipeline
from app.core.rate_limit import limiter

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


class ResearchReportSummary(BaseModel):
    id: int
    stock_code: str
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


@router.post("/{stock_code}", response_model=ResearchReportFull)
@limiter.limit(TRIGGER_RATE_LIMIT)
def trigger_research(
    request: Request,
    stock_code: str,
    payload: ResearchTriggerRequest | None = None,
    db: Session = Depends(get_db),
) -> ResearchReportFull:
    """Trigger deep_research_pipeline for a stock.

    Skips if existing research within 30 days, unless force=True.
    Pre-checks monthly budget before running.
    Rate-limited to 10/min (per security review).
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

    # 30-day cache check (unless force)
    if not payload.force and not lifecycle_service.needs_research(db, stock_code, cache_days=30):
        latest = _get_latest_report(db, stock_code)
        if latest:
            return _to_full_response(latest)

    # Map model tier string to GLMTier
    from app.services.llm.client import GLMTier
    tier_map = {
        "sonnet": GLMTier.SONNET,
        "opus": GLMTier.OPUS,
        "haiku": GLMTier.HAIKU,
    }
    tier = tier_map.get(payload.model_tier.lower(), GLMTier.SONNET)

    try:
        result = deep_research_pipeline.run(
            stock_code,
            model_tier=tier,
            use_web_search=payload.use_web_search,
            db_session=db,
        )
        db.commit()
    except ValueError as exc:
        # Known validation errors — safe to surface
        db.rollback()
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        # Log details server-side, return generic message (per security review)
        db.rollback()
        logger.exception("deep_research failed for %s", stock_code)
        raise HTTPException(502, "deep_research failed; see server logs") from exc

    # Fetch persisted report
    report = db.query(ResearchReport).filter(
        ResearchReport.id == result.report_id
    ).first()
    if report is None:
        raise HTTPException(500, "report not persisted")
    return _to_full_response(report)


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
    rows = (
        db.query(ResearchReport)
        .filter(ResearchReport.stock_code == stock_code)
        .order_by(desc(ResearchReport.created_at))
        .limit(limit)
        .all()
    )
    return [_to_summary(r) for r in rows]


@router.get("/reports", response_model=list[ResearchReportSummary])
def list_recent_reports(
    pipeline_type: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[ResearchReportSummary]:
    """Recent reports across all stocks."""
    q = db.query(ResearchReport)
    if pipeline_type:
        q = q.filter(ResearchReport.pipeline_type == pipeline_type)
    rows = q.order_by(desc(ResearchReport.created_at)).limit(limit).all()
    return [_to_summary(r) for r in rows]


# ── Helpers ──────────────────────────────────────────────────────────────


def _get_latest_report(db: Session, stock_code: str) -> ResearchReport | None:
    return (
        db.query(ResearchReport)
        .filter(ResearchReport.stock_code == stock_code)
        .order_by(desc(ResearchReport.created_at))
        .first()
    )


def _to_summary(r: ResearchReport) -> ResearchReportSummary:
    return ResearchReportSummary(
        id=r.id,
        stock_code=r.stock_code,
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
