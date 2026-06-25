"""TDD for theme_scan_pipeline (serenity engine, trading-philosophy.md §2).

Mocked LLMClient returns per-step outputs; tests cover code validation against
the A-share master, scarcity-score ranking, persistence, and the empty path.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from app.db.session import SessionLocal
from app.models.stock import Stock
from app.models.theme_scan_report import ThemeScanReport
from app.services.llm.client import LLMClient, LLMResponse
from app.services.pipelines.llm import theme_scan_pipeline


def _mk_stock(db, code, name):
    db.add(Stock(code=code, name=name, industry="non_financial", listed_date=date(2010, 1, 1)))


def _resp(args: dict) -> LLMResponse:
    return LLMResponse(
        content="", tool_call_args=args,
        usage={"tokens_in": 800, "tokens_out": 200, "search_count": 1},
        cost_usd=0.001, latency_ms=400, model="glm-5.1",
    )


def _mock_client(universe_candidates: list, ranked: list) -> MagicMock:
    client = MagicMock(spec=LLMClient)
    steps = {
        "system_change": {"theme": "CPO 光模块", "system_change": "800G 切换驱动光引擎",
                          "key_constraint": "bandwidth", "demand_drivers": ["AI 算力"]},
        "value_chain": {"layers": [{"name": "光引擎", "role": "光电转换"},
                                   {"name": "PCB", "role": "承载"}]},
        "scarce_layer": {"ranked_layers": [{"layer": "光引擎", "rank": 1, "scarcity_rationale": "认证周期长"}],
                         "lower_ranked_obvious_layer": "PCB：供应商多"},
        "company_universe": {"candidates": universe_candidates},
        "candidate_rank": {"ranked": ranked, "evidence_grade": "B", "markdown_report": "# CPO 主题"},
    }

    def _complete(**kwargs):
        pt = kwargs.get("pipeline_type", "")
        for name, out in steps.items():
            if pt.endswith(name):
                return _resp(out)
        return _resp({})

    client.complete = MagicMock(side_effect=_complete)
    return client


def test_theme_scan_end_to_end_ranks_validates_persists(setup_db):
    db = SessionLocal()
    try:
        _mk_stock(db, "300308", "中际旭创")
        _mk_stock(db, "002463", "沪电股份")
        db.commit()

        universe = [
            {"code": "300308", "name": "中际旭创", "layer": "光引擎", "classification": "controls"},
            {"code": "002463", "name": "沪电股份", "layer": "PCB", "classification": "benefits"},
            {"code": "999999", "name": "幽灵公司", "layer": "光引擎", "classification": "story"},  # fabricated
        ]
        ranked = [
            {"code": "002463", "name": "沪电股份", "layer": "PCB", "chain_position": "benefits",
             "scarcity_score": 3.0, "thesis": "受益"},
            {"code": "300308", "name": "中际旭创", "layer": "光引擎", "chain_position": "controls",
             "scarcity_score": 4.6, "thesis": "卡点龙头"},
        ]
        result = theme_scan_pipeline.run(
            "CPO 光模块", db_session=db, llm_client=_mock_client(universe, ranked)
        )

        # fabricated A-share code dropped during validation
        assert "999999" in result.dropped_codes
        # ranked sorted by scarcity_score desc (4.6 before 3.0)
        assert [c["code"] for c in result.ranked_candidates] == ["300308", "002463"]
        assert result.ranked_candidates[0]["scarcity_score"] == 4.6
        assert result.status == "completed"
        assert result.report_id is not None

        rep = db.query(ThemeScanReport).filter_by(theme="CPO 光模块").one()
        assert rep.ranked_candidates_json[0]["code"] == "300308"
        assert rep.evidence_grade == "B"
        assert rep.ranked_layers_json[0]["layer"] == "光引擎"
    finally:
        db.close()


def test_theme_scan_empty_when_no_valid_code(setup_db):
    db = SessionLocal()
    try:
        # no stocks inserted → every proposed code is fabricated → empty result
        universe = [{"code": "999999", "name": "幽灵", "layer": "光引擎", "classification": "story"}]
        client = _mock_client(universe, [])
        result = theme_scan_pipeline.run("CPO 光模块", db_session=db, llm_client=client)

        assert result.status == "empty"
        assert result.ranked_candidates == []
        assert "999999" in result.dropped_codes
        # candidate_rank step must be short-circuited (not called)
        called = [c.kwargs.get("pipeline_type") for c in client.complete.call_args_list]
        assert not any(t and t.endswith("candidate_rank") for t in called)
        # but the empty report is still persisted
        assert db.query(ThemeScanReport).filter_by(theme="CPO 光模块").count() == 1
    finally:
        db.close()


def test_theme_scan_api_trigger(setup_db):
    """POST /api/theme-scan runs the pipeline via API and returns ranked list."""
    import os
    os.environ["SCHEDULER_ENABLED"] = "false"
    from app.main import app
    from fastapi.testclient import TestClient

    db = SessionLocal()
    try:
        _mk_stock(db, "300308", "中际旭创")
        db.commit()
    finally:
        db.close()

    universe = [{"code": "300308", "name": "中际旭创", "layer": "光引擎", "classification": "controls"}]
    ranked = [{"code": "300308", "name": "中际旭创", "layer": "光引擎",
               "chain_position": "controls", "scarcity_score": 4.6, "thesis": "卡点龙头"}]
    mock_client = _mock_client(universe, ranked)

    with patch(
        "app.services.pipelines.llm.theme_scan_pipeline.get_llm_client",
        return_value=mock_client,
    ):
        with TestClient(app) as client:
            resp = client.post("/api/theme-scan", json={"theme": "CPO 光模块"})
            assert resp.status_code == 200, resp.text
            data = resp.json()
            assert data["theme"] == "CPO 光模块"
            assert data["status"] == "completed"
            assert data["ranked_candidates"][0]["code"] == "300308"
            assert data["ranked_candidates"][0]["scarcity_score"] == 4.6
