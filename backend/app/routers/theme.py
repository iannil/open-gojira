"""Theme router — CRUD and analysis endpoints."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.common import OkResponse
from app.schemas.theme import ThemeCreate, ThemeResponse, ThemeUpdate
from app.services import theme_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/themes", tags=["themes"])


@router.get("", response_model=list[ThemeResponse])
def list_themes(db: Session = Depends(get_db)):
    """List all themes."""
    themes = theme_service.list_themes(db)
    return themes


@router.post("", response_model=ThemeResponse)
def create_theme(theme_data: ThemeCreate, db: Session = Depends(get_db)):
    """Create a new theme."""
    try:
        theme = theme_service.create_theme(
            db,
            name=theme_data.name,
            description=theme_data.description,
            target_weight_pct=theme_data.target_weight_pct,
        )
        return theme
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to create theme")
        raise HTTPException(status_code=400, detail="Failed to create theme") from exc


@router.get("/{theme_id}", response_model=ThemeResponse)
def get_theme(theme_id: int, db: Session = Depends(get_db)):
    """Get a single theme by ID."""
    theme = theme_service.get_theme(db, theme_id)
    if not theme:
        raise HTTPException(status_code=404, detail="Theme not found")
    return theme


@router.put("/{theme_id}", response_model=ThemeResponse)
def update_theme(theme_id: int, theme_data: ThemeUpdate, db: Session = Depends(get_db)):
    """Update an existing theme."""
    theme = theme_service.update_theme(
        db,
        theme_id,
        name=theme_data.name,
        description=theme_data.description,
        target_weight_pct=theme_data.target_weight_pct,
    )
    if not theme:
        raise HTTPException(status_code=404, detail="Theme not found")
    return theme


@router.delete("/{theme_id}", response_model=OkResponse)
def delete_theme(theme_id: int, db: Session = Depends(get_db)):
    """Delete a theme."""
    success = theme_service.delete_theme(db, theme_id)
    if not success:
        raise HTTPException(status_code=404, detail="Theme not found")
    return {"ok": True}


@router.get("/exposure/analysis")
def get_theme_exposure(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Get current theme exposure analysis."""
    exposure = theme_service.get_theme_exposure(db)
    targets = theme_service.get_theme_targets(db)
    coverage = theme_service.get_theme_coverage(db)

    return {
        "exposure": exposure,
        "targets": targets,
        "coverage": coverage,
    }
