"""Tests for research scheduler service.

Covers Q6 weekly cron + Q12 skip last_run_status='failed'.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from app.models.research_theme import ResearchTheme
from app.services.research_scheduler_service import _is_due, run_due_research_themes


@pytest.fixture
def active_weekly_theme(db_session):
    theme = ResearchTheme(
        name="周更主题", market="A_SHARE", status="active",
        auto_refresh_freq="weekly",
    )
    db_session.add(theme)
    db_session.flush()
    return theme


def test_is_due_weekly_on_monday():
    """Q6: weekly theme due on Mondays."""
    theme = ResearchTheme(name="t", market="A_SHARE",
                          auto_refresh_freq="weekly", status="active")
    monday = date(2026, 6, 15)  # Monday
    assert _is_due(theme, monday) is True


def test_is_due_weekly_not_on_tuesday():
    """Q6: weekly theme not due on Tuesdays."""
    theme = ResearchTheme(name="t", market="A_SHARE",
                          auto_refresh_freq="weekly", status="active")
    tuesday = date(2026, 6, 16)
    assert _is_due(theme, tuesday) is False


def test_is_due_monthly_on_first():
    """Q6: monthly theme due on the 1st."""
    theme = ResearchTheme(name="t", market="A_SHARE",
                          auto_refresh_freq="monthly", status="active")
    assert _is_due(theme, date(2026, 6, 1)) is True
    assert _is_due(theme, date(2026, 6, 15)) is False


def test_is_due_manual_never():
    """Manual freq never triggers scheduler."""
    theme = ResearchTheme(name="t", market="A_SHARE",
                          auto_refresh_freq="manual", status="active")
    assert _is_due(theme, date(2026, 6, 15)) is False


def test_scheduler_skips_failed_themes(db_session, active_weekly_theme, monkeypatch):
    """Q12: themes with last_run_status='failed' are skipped."""
    active_weekly_theme.last_run_status = "failed"
    db_session.flush()
    theme_id = active_weekly_theme.id  # capture before service may close session

    # Force today = Monday
    monday = date(2026, 6, 15)
    monkeypatch.setattr(
        "app.services.research_scheduler_service.date",
        type("D", (), {"today": staticmethod(lambda: monday)}),
    )
    # Patch SessionLocal so scheduler uses the test session
    monkeypatch.setattr(
        "app.services.research_scheduler_service.SessionLocal",
        lambda: db_session,
    )

    triggered_calls = []
    def fake_trigger(db, theme_id, triggered_by="scheduler"):
        triggered_calls.append(theme_id)
        return type("Run", (), {"id": 1})()

    with patch("app.services.research_scheduler_service.trigger_run", fake_trigger):
        result = run_due_research_themes()

    assert theme_id in result["skipped_failed"]
    assert theme_id not in triggered_calls


def test_scheduler_triggers_due_themes(db_session, active_weekly_theme, monkeypatch):
    """Q6: weekly theme on Monday gets triggered."""
    monday = date(2026, 6, 15)
    monkeypatch.setattr(
        "app.services.research_scheduler_service.date",
        type("D", (), {"today": staticmethod(lambda: monday)}),
    )
    monkeypatch.setattr(
        "app.services.research_scheduler_service.SessionLocal",
        lambda: db_session,
    )

    with patch("app.services.research_scheduler_service.trigger_run") as mock_trigger:
        mock_trigger.return_value = type("Run", (), {
            "id": 1, "research_theme_id": active_weekly_theme.id,
        })()
        result = run_due_research_themes()

    assert mock_trigger.called
    assert len(result["triggered"]) >= 1
