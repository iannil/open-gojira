"""End-to-end mock LLM tests for serenity runner.

Tests the full flow: trigger_run → worker → LLM (mocked) → persistence → EventBus.
Uses a synchronous executor to avoid race conditions in tests.

Note on session reuse: `_SyncExecutor` runs the worker in the calling thread.
The worker's `db.close()` in `finally` closes the test session — but SQLAlchemy
sessions are reusable after close (lazily reopen on next query), so subsequent
`db_session.query(...)` calls in the test still work. This is intentional but
subtle; if it ever breaks, switch to using `TestSessionLocal` directly instead
of monkeypatching `SessionLocal` to a lambda.
"""
from __future__ import annotations

from concurrent.futures import Future
from unittest.mock import patch

import pytest

from app.core.events import (
    MonthlyBudgetExceeded,
    ResearchRunCompleted,
    ResearchRunFailed,
    bus,
)
from app.models.research_company_ranking import ResearchCompanyRanking
from app.models.research_company_universe import ResearchCompanyUniverse
from app.models.research_evidence import ResearchEvidence
from app.models.research_run import ResearchRun
from app.models.research_theme import ResearchTheme
from app.models.scarce_layer import ScarceLayer
from app.models.stock import Stock
from app.models.value_chain_layer import ValueChainLayer
from app.services.research_runner_service import (
    ResearchRunnerError,
    shutdown_runner_executor,
    trigger_run,
)


@pytest.fixture(autouse=True)
def reset_executor_after_test():
    """Ensure no leaked executor between tests."""
    yield
    shutdown_runner_executor(wait=False)


@pytest.fixture(autouse=True)
def stub_dump_llm_log(monkeypatch):
    """Prevent _dump_llm_log from writing files to real DATA_DIR during tests.

    Tests don't need the on-disk LLM log artifact; this avoids polluting
    `backend/data/llm_logs/` with test run_ids.
    """
    monkeypatch.setattr(
        "app.services.research_runner_service._dump_llm_log",
        lambda *args, **kwargs: None,
    )


@pytest.fixture
def active_theme_with_stock(db_session):
    theme = ResearchTheme(name="E2E 测试", market="A_SHARE", status="active")
    db_session.add(theme)
    db_session.add(Stock(code="300001", name="测试股1"))
    db_session.add(Stock(code="300002", name="测试股2"))
    db_session.add(Stock(code="300003", name="测试股3"))
    db_session.flush()
    return theme


def _valid_llm_output() -> dict:
    """Minimal valid LLM output (matches schema)."""
    return {
        "system_change": "AI 需求驱动",
        "value_chain": [
            {"layer_index": i, "name": f"L{i}", "description": f"层{i}"}
            for i in range(1, 9)
        ],
        "scarce_layers": [
            {"rank": 1, "layer_index": 4, "reason": "稀缺", "difficulty": "high"},
            {"rank": 2, "layer_index": 5, "reason": "稀缺", "difficulty": "medium"},
            {"rank": 3, "layer_index": 7, "reason": "稀缺", "difficulty": "high"},
        ],
        "company_universe": [
            {"stock_code": "300001", "name": "测试股1", "classification": "controls",
             "layer_index": 4}
            for _ in range(25)
        ],
        "evidence": [
            {"source_url": f"http://e{i}.x", "source_title": f"E{i}",
             "source_type": "filing", "grade": "strong", "summary": f"摘要{i}",
             "stock_code": "300001"}
            for i in range(30)
        ],
        "company_ranking": [
            {"rank": 1, "stock_code": "300001", "name": "测试股1",
             "constrains_what": "环节1", "chain_position": "层4",
             "rank_reason": "原因", "evidence_summary": "证据", "main_risk": "风险"},
            {"rank": 2, "stock_code": "300002", "name": "测试股2",
             "constrains_what": "环节2", "chain_position": "层5",
             "rank_reason": "原因", "evidence_summary": "证据", "main_risk": "风险"},
            {"rank": 3, "stock_code": "300003", "name": "测试股3",
             "constrains_what": "环节3", "chain_position": "层7",
             "rank_reason": "原因", "evidence_summary": "证据", "main_risk": "风险"},
        ],
        "failure_conditions": ["需求放缓"],
        "next_steps": ["查年报"],
    }


class _SyncExecutor:
    """Fake executor that runs submitted tasks synchronously in the calling thread.

    Avoids race conditions in tests where worker uses its own SessionLocal().
    """

    def submit(self, fn, /, *args, **kwargs):
        future: Future = Future()
        try:
            result = fn(*args, **kwargs)
            future.set_result(result)
        except BaseException as exc:
            future.set_exception(exc)
        return future

    def shutdown(self, wait=True, cancel_futures=False):
        pass


def test_trigger_run_full_flow_persists_6_tables(
    db_session, active_theme_with_stock, monkeypatch
):
    """E2E: mock LLM valid output → 6 child tables all written + status completed."""
    # Patch executor so worker runs synchronously in caller thread
    monkeypatch.setattr(
        "app.services.research_runner_service._get_runner_executor",
        lambda: _SyncExecutor(),
    )

    completed_events: list[ResearchRunCompleted] = []
    bus.subscribe(ResearchRunCompleted, completed_events.append)

    with patch(
        "app.services.llm.zhipu_client.get_zhipu_client"
    ) as mock_get_client:
        mock_client = mock_get_client.return_value
        mock_client.run_serenity_research.return_value = _valid_llm_output()
        # Patch SessionLocal to use test session (so worker writes to same DB)
        monkeypatch.setattr(
            "app.services.research_runner_service.SessionLocal",
            lambda: db_session,
        )

        theme_id = active_theme_with_stock.id
        run = trigger_run(db_session, theme_id=theme_id)
        run_id = run.id

    # Re-query fresh (worker thread may have closed the original session)
    fresh_run = db_session.query(ResearchRun).filter(ResearchRun.id == run_id).first()
    assert fresh_run is not None
    assert fresh_run.status == "completed"
    assert fresh_run.llm_token_input == 0  # mock returns no usage
    assert fresh_run.system_change_md == "AI 需求驱动"

    theme = db_session.query(ResearchTheme).first()
    assert theme.last_run_status == "completed"
    assert theme.last_run_at is not None

    # Verify 6 child tables
    assert db_session.query(ValueChainLayer).count() == 8
    assert db_session.query(ScarceLayer).count() == 3
    assert db_session.query(ResearchCompanyUniverse).count() == 25
    assert db_session.query(ResearchEvidence).count() == 30
    assert db_session.query(ResearchCompanyRanking).count() == 3

    # Verify EventBus emit
    assert len(completed_events) == 1
    assert completed_events[0].research_theme_id == theme_id
    assert completed_events[0].company_count == 25


def test_trigger_run_failure_marks_failed_and_emits_event(
    db_session, active_theme_with_stock, monkeypatch
):
    """E2E: LLM raises → run marked failed + retry exhausted + ResearchRunFailed emitted."""
    monkeypatch.setattr(
        "app.services.research_runner_service._get_runner_executor",
        lambda: _SyncExecutor(),
    )
    # Reduce retry to 0 to fail fast
    from app.core import research_config
    no_retry_cfg = {**research_config.SERENITY_RUN_CONFIG, "retry_on_failure": 0}
    monkeypatch.setattr(
        "app.services.research_runner_service.SERENITY_RUN_CONFIG",
        no_retry_cfg,
    )

    failed_events: list[ResearchRunFailed] = []
    bus.subscribe(ResearchRunFailed, failed_events.append)

    from app.services.llm.zhipu_client import ZhipuClientError

    with patch(
        "app.services.llm.zhipu_client.get_zhipu_client"
    ) as mock_get_client:
        mock_client = mock_get_client.return_value
        mock_client.run_serenity_research.side_effect = ZhipuClientError("GLM 429 quota exceeded")
        monkeypatch.setattr(
            "app.services.research_runner_service.SessionLocal",
            lambda: db_session,
        )

        theme_id = active_theme_with_stock.id
        run = trigger_run(db_session, theme_id=theme_id)
        run_id = run.id

    fresh_run = db_session.query(ResearchRun).filter(ResearchRun.id == run_id).first()
    assert fresh_run is not None
    assert fresh_run.status == "failed"
    assert "GLM 429" in (fresh_run.error_message or "")

    theme = db_session.query(ResearchTheme).first()
    assert theme.last_run_status == "failed"
    assert "GLM 429" in (theme.last_run_error or "")

    assert len(failed_events) == 1
    assert failed_events[0].error.startswith("GLM 429")


def test_monthly_budget_check_emits_event_when_exceeded(
    db_session, active_theme_with_stock, monkeypatch
):
    """Q8: when monthly spend > budget, MonthlyBudgetExceeded is emitted."""
    monkeypatch.setattr(
        "app.services.research_runner_service._get_runner_executor",
        lambda: _SyncExecutor(),
    )
    # Force budget very low so any token spend triggers
    from app.core import research_config
    low_budget_cfg = {**research_config.SERENITY_RUN_CONFIG, "monthly_budget_cny": 0.001}
    monkeypatch.setattr(
        "app.services.research_runner_service.SERENITY_RUN_CONFIG",
        low_budget_cfg,
    )

    budget_events: list[MonthlyBudgetExceeded] = []
    bus.subscribe(MonthlyBudgetExceeded, budget_events.append)

    output = _valid_llm_output()
    output["_usage"] = {"token_input": 1000, "token_output": 500, "search_count": 5}

    with patch(
        "app.services.llm.zhipu_client.get_zhipu_client"
    ) as mock_get_client:
        mock_client = mock_get_client.return_value
        mock_client.run_serenity_research.return_value = output
        monkeypatch.setattr(
            "app.services.research_runner_service.SessionLocal",
            lambda: db_session,
        )

        theme_id = active_theme_with_stock.id
        run = trigger_run(db_session, theme_id=theme_id)
        run_id = run.id

    fresh_run = db_session.query(ResearchRun).filter(ResearchRun.id == run_id).first()
    assert fresh_run is not None
    assert fresh_run.status == "completed"
    assert fresh_run.llm_token_input == 1000

    # Spend = (1000+500)/1000 * 0.005 = 0.0075 CNY > 0.001 budget → event fires
    assert len(budget_events) == 1
    assert budget_events[0].spend_cny > budget_events[0].budget_cny
    assert budget_events[0].triggered_by_run_id == run_id

