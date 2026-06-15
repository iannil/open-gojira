"""Scheduler service for auto-refresh research themes.

Q6: runs weekly (Monday 8am Asia/Shanghai) for themes with
auto_refresh_freq='weekly'. Q12: skips themes with last_run_status='failed'
to avoid burning tokens on a known-broken theme.
"""
from __future__ import annotations

import logging
from datetime import date

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.research_theme import ResearchTheme
from app.services.research_runner_service import (
    ResearchRunnerError,
    trigger_run,
)

logger = logging.getLogger(__name__)


def run_due_research_themes() -> dict:
    """Scheduled entry point: trigger all due themes.

    Returns {"triggered": [...], "skipped_failed": [...], "errors": [...]}.
    """
    today = date.today()
    triggered: list[int] = []
    skipped_failed: list[int] = []
    errors: list[dict] = []

    db = SessionLocal()
    try:
        themes = (
            db.query(ResearchTheme)
            .filter(
                ResearchTheme.status == "active",
                ResearchTheme.auto_refresh_freq.in_(["weekly", "monthly"]),
            )
            .all()
        )

        for theme in themes:
            if not _is_due(theme, today):
                continue
            if theme.last_run_status == "failed":
                skipped_failed.append(theme.id)
                logger.info(
                    "Skipping theme_id=%s name=%r — last_run_status='failed'",
                    theme.id, theme.name,
                )
                continue

            try:
                run = trigger_run(
                    db=db,
                    theme_id=theme.id,
                    triggered_by="scheduler",
                )
                triggered.append(run.id)
            except ResearchRunnerError as exc:
                errors.append({"theme_id": theme.id, "error": str(exc)})
                logger.warning(
                    "Scheduler trigger failed for theme_id=%s: %s",
                    theme.id, exc,
                )

        db.commit()
    finally:
        db.close()

    return {
        "triggered": triggered,
        "skipped_failed": skipped_failed,
        "errors": errors,
    }


def _is_due(theme: ResearchTheme, today: date) -> bool:
    """Check whether a theme is due to run today.

    - weekly: run on Mondays (weekday 0)
    - monthly: run on the 1st of each month
    """
    if theme.auto_refresh_freq == "weekly":
        return today.weekday() == 0  # Monday
    if theme.auto_refresh_freq == "monthly":
        return today.day == 1
    return False
