"""Tests for /api/business-patterns router."""

from __future__ import annotations

import pytest

from app.models.stock import Stock
from tests.conftest import TestSessionLocal


@pytest.fixture
def db():
    s = TestSessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.main import app

    return TestClient(app)


def test_list_empty(client):
    """Empty DB returns empty list."""
    r = client.get("/api/business-patterns")
    assert r.status_code == 200
    assert r.json() == []


def test_create_and_get(client):
    payload = {
        "name": "测试模式",
        "description": "desc",
        "first_principle_variable": "X",
        "power_tier_baseline": 2,
        "thesis_variables": [{"name": "v1", "unit": "%", "source": "manual"}],
        "lixinger_industries": ["测试行业"],
    }
    r = client.post("/api/business-patterns", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "测试模式"
    assert body["is_builtin"] is False
    assert body["id"] > 0
    pattern_id = body["id"]

    # GET by id
    r = client.get(f"/api/business-patterns/{pattern_id}")
    assert r.status_code == 200
    assert r.json()["name"] == "测试模式"


def test_create_rejects_source_ref_for_user(client):
    """User-created patterns cannot carry source_ref. Pydantic raises 422."""
    payload = {
        "name": "用户",
        "source_ref": "should be rejected",
    }
    r = client.post("/api/business-patterns", json=payload)
    assert r.status_code == 422


def test_update_description_only_for_builtin(client, db):
    """Builtin rows: only description editable."""
    # Insert a builtin pattern directly
    from app.models.business_pattern import BusinessPattern

    bp = BusinessPattern(
        name="银行",
        first_principle_variable="原始",
        power_tier_baseline=1,
        is_builtin=True,
        source_ref="invest3 §11",
    )
    db.add(bp)
    db.commit()
    db.refresh(bp)

    # description ok
    r = client.patch(
        f"/api/business-patterns/{bp.id}",
        json={"description": "新描述"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["description"] == "新描述"

    # first_principle rejected
    r = client.patch(
        f"/api/business-patterns/{bp.id}",
        json={"first_principle_variable": "试图改"},
    )
    assert r.status_code == 400


def test_update_user_pattern_all_fields(client):
    payload = {"name": "原始", "power_tier_baseline": 1}
    r = client.post("/api/business-patterns", json=payload)
    pattern_id = r.json()["id"]

    r = client.patch(
        f"/api/business-patterns/{pattern_id}",
        json={
            "name": "改名",
            "power_tier_baseline": 3,
            "first_principle_variable": "新核心",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "改名"
    assert body["power_tier_baseline"] == 3
    assert body["first_principle_variable"] == "新核心"


def test_delete_builtin_refused(client, db):
    from app.models.business_pattern import BusinessPattern

    bp = BusinessPattern(name="银行", power_tier_baseline=1, is_builtin=True)
    db.add(bp)
    db.commit()
    db.refresh(bp)

    r = client.delete(f"/api/business-patterns/{bp.id}")
    assert r.status_code == 400


def test_delete_user_pattern_clears_stock(client, db):
    from app.models.business_pattern import BusinessPattern

    bp = BusinessPattern(name="用户", power_tier_baseline=0, is_builtin=False)
    db.add(bp)
    db.commit()
    db.refresh(bp)

    stock = Stock(code="600001", name="X", business_pattern_id=bp.id)
    db.add(stock)
    db.commit()

    r = client.delete(f"/api/business-patterns/{bp.id}")
    assert r.status_code == 200
    assert r.json() == {"ok": True}

    db.expire_all()
    refreshed = db.get(Stock, "600001")
    assert refreshed.business_pattern_id is None


def test_get_thesis_templates(client, db):
    from app.models.business_pattern import BusinessPattern

    bp = BusinessPattern(
        name="银行",
        power_tier_baseline=1,
        is_builtin=True,
        thesis_variables_json=(
            '[{"name": "不良贷款率", "unit": "%", "source": "lixinger"}]'
        ),
    )
    db.add(bp)
    db.commit()
    db.refresh(bp)

    r = client.get(f"/api/business-patterns/{bp.id}/thesis-templates")
    assert r.status_code == 200
    body = r.json()
    assert body["pattern_id"] == bp.id
    assert body["pattern_name"] == "银行"
    assert len(body["templates"]) == 1
    assert body["templates"][0]["name"] == "不良贷款率"


def test_infer_all_endpoint(client, db):
    from app.models.business_pattern import BusinessPattern

    bp = BusinessPattern(
        name="银行",
        power_tier_baseline=1,
        is_builtin=True,
        lixinger_industries_json='["银行"]',
    )
    db.add(bp)
    stock = Stock(code="600036", name="招行", industry="银行")
    db.add(stock)
    db.commit()

    r = client.post("/api/business-patterns/infer-all")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert body["updated"] == 1

    db.expire_all()
    refreshed = db.get(Stock, "600036")
    assert refreshed.business_pattern_id == bp.id


def test_stock_patch_business_pattern(client, db):
    from app.models.business_pattern import BusinessPattern

    bp = BusinessPattern(name="银行", power_tier_baseline=1, is_builtin=True)
    db.add(bp)
    stock = Stock(code="600036", name="招行")
    db.add(stock)
    db.commit()
    db.refresh(bp)

    r = client.patch(
        "/api/stocks/600036/business-pattern",
        json={"business_pattern_id": bp.id},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["business_pattern_id"] == bp.id
    assert body["business_pattern_name"] == "银行"
    assert body["business_pattern_inferred_at"] is None  # manual override marker
