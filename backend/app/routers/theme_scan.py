"""Theme Scan API — serenity engine endpoints (trading-philosophy.md §2).

Exposes:
  POST /api/theme-scan                  trigger theme_scan_pipeline for a theme
  GET  /api/theme-scan/reports          recent theme scans
  GET  /api/theme-scan/{report_id}      one theme scan report

Per decision 1 (single-user, no auth). Budget pre-check + rate limit guard
against accidental spend runaway, mirroring research_v2.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.rate_limit import limiter
from app.db.session import get_db
from app.models.theme_scan_report import ThemeScanReport
from app.services.llm.cost_tracker import check_budget_available
from app.services.pipelines.llm import theme_scan_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/theme-scan", tags=["theme-scan"])

TRIGGER_RATE_LIMIT = "5/minute"


# ── Schemas ───────────────────────────────────────────────────────────────


class ThemeScanRequest(BaseModel):
    theme: str
    model_tier: str = "sonnet"  # sonnet | opus | haiku
    use_web_search: bool = True


class ThemeScanSummary(BaseModel):
    id: int
    theme: str
    evidence_grade: str | None
    status: str
    created_at: datetime | None


class ThemeScanFull(ThemeScanSummary):
    system_change: str | None
    ranked_layers: list[dict] | None
    ranked_candidates: list[dict] | None
    markdown_output: str | None
    prompt_version: str | None


# ── Endpoints ────────────────────────────────────────────────────────────


@router.post("", response_model=ThemeScanFull)
@limiter.limit(TRIGGER_RATE_LIMIT)
def trigger_theme_scan(
    request: Request,
    payload: ThemeScanRequest,
    db: Session = Depends(get_db),
) -> ThemeScanFull:
    """Run the serenity theme_scan workflow for one theme.

    Produces a ranked bottleneck candidate list. Convert a pick to a buy
    decision via POST /api/research/{code} with source=theme_scan +
    scarcity_score (trading-philosophy.md §2, manual handoff).
    """
    theme = payload.theme.strip()
    if not theme:
        raise HTTPException(400, "theme must not be empty")

    allowed, reason = check_budget_available(db)
    if not allowed:
        raise HTTPException(429, f"LLM budget exhausted: {reason}")

    from app.services.llm.client import GLMTier
    tier_map = {"sonnet": GLMTier.SONNET, "opus": GLMTier.OPUS, "haiku": GLMTier.HAIKU}
    tier = tier_map.get(payload.model_tier.lower(), GLMTier.SONNET)

    try:
        result = theme_scan_pipeline.run(
            theme,
            model_tier=tier,
            use_web_search=payload.use_web_search,
            db_session=db,
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("theme_scan failed for theme=%s", theme)
        raise HTTPException(502, "theme_scan failed; see server logs") from exc

    report = db.query(ThemeScanReport).filter(
        ThemeScanReport.id == result.report_id
    ).first()
    if report is None:
        raise HTTPException(500, "report not persisted")
    return _to_full(report)


@router.get("/reports", response_model=list[ThemeScanSummary])
def list_recent(limit: int = 20, db: Session = Depends(get_db)) -> list[ThemeScanSummary]:
    rows = (
        db.query(ThemeScanReport)
        .order_by(desc(ThemeScanReport.created_at))
        .limit(min(limit, 100))
        .all()
    )
    return [_to_summary(r) for r in rows]


@router.get("/{report_id}", response_model=ThemeScanFull)
def get_report(report_id: int, db: Session = Depends(get_db)) -> ThemeScanFull:
    report = db.query(ThemeScanReport).filter(ThemeScanReport.id == report_id).first()
    if report is None:
        raise HTTPException(404, f"theme scan report not found: {report_id}")
    return _to_full(report)


# ── Mappers ──────────────────────────────────────────────────────────────


def _to_summary(r: ThemeScanReport) -> ThemeScanSummary:
    return ThemeScanSummary(
        id=r.id, theme=r.theme, evidence_grade=r.evidence_grade,
        status=r.status, created_at=r.created_at,
    )


def _to_full(r: ThemeScanReport) -> ThemeScanFull:
    return ThemeScanFull(
        id=r.id, theme=r.theme, evidence_grade=r.evidence_grade,
        status=r.status, created_at=r.created_at,
        system_change=r.system_change,
        ranked_layers=r.ranked_layers_json,
        ranked_candidates=r.ranked_candidates_json,
        markdown_output=r.markdown_output,
        prompt_version=r.prompt_version,
    )
