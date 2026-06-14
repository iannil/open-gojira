"""Business patterns router — CRUD + inference trigger + thesis templates.

Maps to invest docs methodology (生意模式). See models/business_pattern.py.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.business_pattern import (
    BusinessPatternCreate,
    BusinessPatternResponse,
    BusinessPatternUpdate,
    ThesisTemplateResponse,
)
from app.schemas.common import OkResponse
from app.services import business_pattern_service as svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/business-patterns", tags=["business-patterns"])


def _serialize(pattern) -> dict[str, Any]:
    """Convert BusinessPattern ORM to response dict (handles JSON lists)."""
    import json as _json

    def _parse(s, default):
        if not s:
            return default
        try:
            return _json.loads(s)
        except (ValueError, TypeError):
            return default

    return {
        "id": pattern.id,
        "name": pattern.name,
        "theme_id": pattern.theme_id,
        "description": pattern.description,
        "first_principle_variable": pattern.first_principle_variable,
        "power_tier_baseline": pattern.power_tier_baseline,
        "thesis_variables": _parse(pattern.thesis_variables_json, []),
        "lixinger_industries": _parse(pattern.lixinger_industries_json, []),
        "source_ref": pattern.source_ref,
        "is_builtin": pattern.is_builtin,
        "created_at": pattern.created_at,
        "updated_at": pattern.updated_at,
    }


@router.get("", response_model=list[BusinessPatternResponse])
def list_patterns(
    builtin_only: bool = False, db: Session = Depends(get_db)
) -> list[dict[str, Any]]:
    """List all business patterns. Pass builtin_only=true to filter."""
    patterns = svc.list_patterns(db, include_builtin_only=builtin_only)
    return [_serialize(p) for p in patterns]


@router.post("", response_model=BusinessPatternResponse)
def create_pattern(
    payload: BusinessPatternCreate, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Create a new (user-defined) business pattern.

    source_ref is reserved for builtin patterns and rejected here.
    """
    try:
        pattern = svc.create_pattern(
            db,
            name=payload.name,
            theme_id=payload.theme_id,
            description=payload.description,
            first_principle_variable=payload.first_principle_variable,
            power_tier_baseline=payload.power_tier_baseline,
            thesis_variables=[v.model_dump() for v in payload.thesis_variables],
            lixinger_industries=payload.lixinger_industries,
            source_ref=payload.source_ref,
            is_builtin=False,  # user-created always
        )
        return _serialize(pattern)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        logger.exception("Failed to create business pattern")
        raise HTTPException(status_code=400, detail="Failed to create") from e


@router.get("/{pattern_id}", response_model=BusinessPatternResponse)
def get_pattern(pattern_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    pattern = svc.get_pattern(db, pattern_id)
    if pattern is None:
        raise HTTPException(status_code=404, detail="BusinessPattern not found")
    return _serialize(pattern)


@router.patch("/{pattern_id}", response_model=BusinessPatternResponse)
def update_pattern(
    pattern_id: int,
    payload: BusinessPatternUpdate,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Update a business pattern.

    Builtin rows: only description editable (other fields rejected with 400).
    User-created rows: all fields editable.
    """
    try:
        pattern = svc.update_pattern(
            db,
            pattern_id,
            name=payload.name,
            theme_id=payload.theme_id,
            description=payload.description,
            first_principle_variable=payload.first_principle_variable,
            power_tier_baseline=payload.power_tier_baseline,
            thesis_variables=(
                [v.model_dump() for v in payload.thesis_variables]
                if payload.thesis_variables is not None
                else None
            ),
            lixinger_industries=payload.lixinger_industries,
            source_ref=payload.source_ref,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if pattern is None:
        raise HTTPException(status_code=404, detail="BusinessPattern not found")
    return _serialize(pattern)


@router.delete("/{pattern_id}", response_model=OkResponse)
def delete_pattern(pattern_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    """Delete a business pattern. Refuses builtin rows.

    Stocks referencing the pattern will have their business_pattern_id cleared.
    """
    try:
        success = svc.delete_pattern(db, pattern_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not success:
        raise HTTPException(status_code=404, detail="BusinessPattern not found")
    return {"ok": True}


@router.post("/infer-all")
def infer_all_patterns(
    force: bool = False, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Manually trigger batch re-inference of Stock.business_pattern_id.

    By default skips stocks with manual override (inferred_at IS NULL with
    non-NULL business_pattern_id). Pass force=true to re-infer all stocks.
    """
    summary = svc.infer_all_stocks(db, force=force)
    db.commit()
    return summary


@router.get("/{pattern_id}/thesis-templates", response_model=ThesisTemplateResponse)
def get_thesis_templates(
    pattern_id: int, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Return thesis variable templates for a pattern (for 'load from template' UI)."""
    result = svc.get_thesis_templates(db, pattern_id)
    if result is None:
        raise HTTPException(status_code=404, detail="BusinessPattern not found")
    return result
