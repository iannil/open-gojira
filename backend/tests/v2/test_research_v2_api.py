"""API tests for the async deep_research trigger (research_v2).

The deep_research pipeline is a multi-minute LLM job, so POST /api/research/
{code} runs it in the background: it returns 202 immediately with a "running"
placeholder whose status flips to terminal when the job finishes. These tests
mock deep_research_pipeline.run (no real LLM calls) and rely on Starlette's
TestClient running BackgroundTasks synchronously after the response.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

from app.models.research_report import (
    PIPELINE_DEEP_RESEARCH,
    STATUS_COMPLETED,
    STATUS_RUNNING,
    ResearchReport,
)
from app.models.stock import Stock
from app.services.pipelines.llm import deep_research_pipeline

CODE = "002378"


@pytest.fixture
def seeded_stock(db_session):
    db_session.add(Stock(code=CODE, name="章源钨业", industry="non_financial",
                         listed_date=date(2010, 5, 18)))
    db_session.commit()
    yield


def _fake_run_completed(stock_code, *, existing_report_id, db_session, **kwargs):
    """Simulate the real pipeline: update the placeholder row in place."""
    report = db_session.query(ResearchReport).filter(
        ResearchReport.id == existing_report_id
    ).first()
    report.status = STATUS_COMPLETED
    report.overall_score = 4.2
    report.recommendation = "BUY"
    return MagicMock(report_id=existing_report_id)


def test_trigger_returns_202_running(client, seeded_stock, monkeypatch):
    spy = MagicMock(side_effect=_fake_run_completed)
    monkeypatch.setattr(deep_research_pipeline, "run", spy)

    resp = client.post(f"/api/research/{CODE}", json={"force": True})

    assert resp.status_code == 202
    body = resp.json()
    # The response is serialized before the background task runs → still running.
    assert body["status"] == STATUS_RUNNING
    assert body["stock_code"] == CODE
    assert body["pipeline_type"] == PIPELINE_DEEP_RESEARCH
    # Background task ran (TestClient runs it after the response).
    assert spy.call_count == 1


def test_background_completion_updates_same_row(client, seeded_stock, db_session, monkeypatch):
    monkeypatch.setattr(deep_research_pipeline, "run",
                        MagicMock(side_effect=_fake_run_completed))

    client.post(f"/api/research/{CODE}", json={"force": True})

    # No duplicate row: the placeholder was updated in place, not re-inserted.
    rows = db_session.query(ResearchReport).filter(
        ResearchReport.stock_code == CODE
    ).all()
    assert len(rows) == 1
    assert rows[0].status == STATUS_COMPLETED
    assert rows[0].recommendation == "BUY"

    # /latest reflects the terminal status.
    latest = client.get(f"/api/research/{CODE}/latest").json()
    assert latest["status"] == STATUS_COMPLETED


def test_concurrency_guard_returns_existing_running(client, seeded_stock, db_session, monkeypatch):
    # An in-flight run already exists.
    placeholder = ResearchReport(
        stock_code=CODE, pipeline_type=PIPELINE_DEEP_RESEARCH, status=STATUS_RUNNING,
    )
    db_session.add(placeholder)
    db_session.commit()
    running_id = placeholder.id

    spy = MagicMock(side_effect=_fake_run_completed)
    monkeypatch.setattr(deep_research_pipeline, "run", spy)

    resp = client.post(f"/api/research/{CODE}", json={"force": True})

    assert resp.status_code == 202
    assert resp.json()["id"] == running_id
    # Guard short-circuits: no second job launched, no duplicate row.
    assert spy.call_count == 0
    rows = db_session.query(ResearchReport).filter(
        ResearchReport.stock_code == CODE
    ).all()
    assert len(rows) == 1


def test_background_failure_marks_failed(client, seeded_stock, db_session, monkeypatch):
    monkeypatch.setattr(deep_research_pipeline, "run",
                        MagicMock(side_effect=RuntimeError("LLM exploded")))

    resp = client.post(f"/api/research/{CODE}", json={"force": True})
    assert resp.status_code == 202
    assert resp.json()["status"] == STATUS_RUNNING

    # Background task caught the error and marked the placeholder FAILED.
    latest = client.get(f"/api/research/{CODE}/latest").json()
    assert latest["status"] == "failed"
    assert latest["markdown_output"]  # error note recorded


def test_trigger_unknown_stock_404(client, monkeypatch):
    spy = MagicMock(side_effect=_fake_run_completed)
    monkeypatch.setattr(deep_research_pipeline, "run", spy)

    resp = client.post("/api/research/999999", json={"force": True})

    assert resp.status_code == 404
    assert spy.call_count == 0
