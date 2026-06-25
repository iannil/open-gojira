"""ThemeScanReport model round-trip (trading-philosophy.md §2)."""
from __future__ import annotations

from app.db.session import SessionLocal
from app.models.theme_scan_report import (
    PIPELINE_THEME_SCAN,
    STATUS_COMPLETED,
    ThemeScanReport,
)


def test_pipeline_constant():
    assert PIPELINE_THEME_SCAN == "theme_scan"


def test_theme_scan_report_round_trip(setup_db):
    db = SessionLocal()
    try:
        report = ThemeScanReport(
            theme="CPO 光模块",
            system_change="800G 切换驱动光引擎需求",
            ranked_layers_json=[
                {"layer": "光引擎封装", "scarcity_rationale": "认证周期长", "rank": 1},
                {"layer": "PCB", "scarcity_rationale": "供应商多", "rank": 5},
            ],
            ranked_candidates_json=[
                {
                    "code": "300308", "name": "中际旭创", "layer": "光引擎封装",
                    "chain_position": "controls", "scarcity_score": 4.5,
                    "thesis": "高端光模块龙头", "failure_conditions": ["客户自研"],
                    "evidence": [],
                },
            ],
            json_output={"steps": "..."},
            markdown_output="# CPO 主题扫描",
            evidence_grade="B",
            prompt_version="v1",
            status=STATUS_COMPLETED,
        )
        db.add(report)
        db.commit()
        db.refresh(report)

        assert report.id is not None
        fetched = db.query(ThemeScanReport).filter_by(theme="CPO 光模块").one()
        assert fetched.ranked_layers_json[0]["rank"] == 1
        assert fetched.ranked_candidates_json[0]["scarcity_score"] == 4.5
        assert fetched.status == "completed"
        assert fetched.created_at is not None
    finally:
        db.close()
