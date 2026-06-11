"""daily_plan_run job registry wiring."""

from unittest.mock import patch

from app import scheduler as sched_module


def test_job_registered_in_registry():
    assert "daily_plan_evaluation" in sched_module.JOB_REGISTRY


def test_job_runs_runner(monkeypatch):
    with patch(
        "app.services.plan_runner.run_all_active",
        return_value=[],
    ) as mock_run:
        out = sched_module.daily_plan_evaluation_job()
    mock_run.assert_called_once()
    assert out["evaluated"] == 0
    assert out["drafts_emitted"] == 0
