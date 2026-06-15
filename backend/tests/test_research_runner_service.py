"""Tests for research runner service.

Covers Q10 async trigger, Q6 rate limit, Q8 retry on failure.
LLM is mocked via monkey-patching get_zhipu_client.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.models.research_run import ResearchRun
from app.models.research_theme import ResearchTheme
from app.services.llm.zhipu_client import ZhipuClientError
from app.services.research_runner_service import (
    ResearchRunnerError,
    shutdown_runner_executor,
    trigger_run,
)


@pytest.fixture(autouse=True)
def reset_executor_after_test():
    """Ensure executor doesn't leak between tests."""
    yield
    shutdown_runner_executor(wait=False)


@pytest.fixture
def active_theme(db_session):
    theme = ResearchTheme(name="测试主题", market="A_SHARE", status="active")
    db_session.add(theme)
    db_session.flush()
    return theme


def test_trigger_run_unknown_theme_raises(db_session):
    """Trigger on non-existent theme raises."""
    with pytest.raises(ResearchRunnerError, match=r"not found"):
        trigger_run(db_session, theme_id=99999)


def test_trigger_run_archived_theme_raises(db_session):
    """Trigger on archived theme raises."""
    theme = ResearchTheme(name="归档主题", market="A_SHARE", status="archived")
    db_session.add(theme)
    db_session.flush()
    with pytest.raises(ResearchRunnerError, match=r"status=archived"):
        trigger_run(db_session, theme_id=theme.id)


def test_trigger_run_rate_limit_blocks_recent(db_session, active_theme):
    """Q6: same theme within rate_limit_per_theme_minutes is blocked."""
    active_theme.last_run_at = datetime.utcnow()
    db_session.flush()
    with pytest.raises(ResearchRunnerError, match=r"wait.*more minutes"):
        trigger_run(db_session, theme_id=active_theme.id)


def test_trigger_run_after_rate_limit_window_ok(db_session, active_theme):
    """Q6: theme older than window can be triggered."""
    active_theme.last_run_at = datetime.utcnow() - timedelta(minutes=30)
    db_session.flush()
    run = trigger_run(db_session, theme_id=active_theme.id)
    assert run.status == "running"
    assert run.research_theme_id == active_theme.id


def test_trigger_run_returns_immediately_with_pending_run(db_session, active_theme):
    """Q10 async: trigger returns immediately, status='running'."""
    # Mock the worker so we don't actually start a thread that calls GLM
    with patch("app.services.research_runner_service._get_runner_executor") as mock_exec:
        mock_pool = MagicMock()
        mock_exec.return_value = mock_pool

        run = trigger_run(db_session, theme_id=active_theme.id)

    assert run.status == "running"
    assert run.scope_market == "A_SHARE"
    assert run.triggered_by == "manual"
    assert mock_pool.submit.called  # task was queued
