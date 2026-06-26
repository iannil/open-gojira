"""Test the v2 信号优先 cockpit aggregator (decision 19)."""
from datetime import date, datetime

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.draft import Draft
from app.models.trade import Trade
from app.models.research_report import ResearchReport
from app.models.stock import Stock
from app.models.system_alert import SystemAlert
from app.services import cockpit_service


def _seed(db):
    db.add(Stock(code="600519", name="贵州茅台", industry="non_financial",
                 listed_date=date(2001, 8, 27)))
    db.add(Trade(stock_code="600519", side="BUY", price=1600.0, quantity=100,
                 filled_at=datetime(2026, 6, 11, 10, 0), total_value=160000.0,
                 source="manual"))
    db.add(Draft(code="600519", side="BUY", status="pending",
                 step_kind="aggressive", step_index=0, reason="价格入区间"))
    db.add(SystemAlert(severity="critical", category="data",
                       message="Lixinger token 失效"))
    db.add(ResearchReport(stock_code="600519", pipeline_type="deep_research",
                          overall_score=4.2, recommendation="BUY",
                          evidence_grade="A", status="completed"))
    db.commit()


def test_build_aggregates_v2_sections(setup_db):
    db = SessionLocal()
    try:
        _seed(db)
        out = cockpit_service.build(db)

        assert out["errors"] == []
        # 顶部：待办 drafts
        assert out["drafts_pending_count"] == 1
        assert out["drafts"][0]["code"] == "600519"
        assert out["drafts"][0]["side"] == "BUY"
        # 中部：持仓
        assert len(out["portfolio"]["holdings"]) == 1
        assert out["portfolio"]["summary"] is not None
        # 底部：lifecycle 计数（dict，可能为空 —— 本测试未建 lifecycle）
        assert isinstance(out["pipeline_counts"], dict)
        # 告警
        assert out["alerts"]["critical_count"] == 1
        assert out["alerts"]["items"][0]["severity"] == "critical"
        # 报告
        assert out["recent_reports"][0]["recommendation"] == "BUY"
        assert "as_of" in out
    finally:
        db.close()


def test_cockpit_endpoint_returns_v2_dto(setup_db):
    db = SessionLocal()
    try:
        _seed(db)
    finally:
        db.close()
    with TestClient(app) as client:
        resp = client.get("/api/cockpit")
        assert resp.status_code == 200
        data = resp.json()
        for key in ("drafts", "portfolio", "pipeline_counts", "alerts",
                    "recent_reports", "errors"):
            assert key in data
        assert data["drafts_pending_count"] == 1
        assert data["alerts"]["critical_count"] == 1


def test_build_empty_db_no_errors(setup_db):
    db = SessionLocal()
    try:
        out = cockpit_service.build(db)
        assert out["errors"] == []
        assert out["drafts"] == []
        assert out["portfolio"]["holdings"] == []
        assert out["recent_reports"] == []
    finally:
        db.close()
