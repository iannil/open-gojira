"""Phase 6 Tier 1 — Metrics API endpoints.

Provides aggregate data for the frontend MonitoringPage dashboard.
All endpoints read-only, designed for periodic polling (every 30-60s).
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.metrics_service import (
    get_llm_summary,
    get_llm_trend,
    get_pipeline_summary,
)

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("/pipelines")
def api_pipeline_summary(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    """Pipeline 成功率/失败率 per pipeline type."""
    return get_pipeline_summary(db, days=days)


@router.get("/llm")
def api_llm_summary(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    """LLM 调用汇总: 成本 / token / 冲突率 / 月度预算."""
    return get_llm_summary(db, days=days)


@router.get("/llm/trend")
def api_llm_trend(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    """LLM 日级别趋势 (Sparkline 数据)."""
    return get_llm_trend(db, days=days)
