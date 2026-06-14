"""Tests for business_pattern_service — CRUD + inference logic."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.business_pattern import BusinessPattern
from app.models.stock import Stock
from app.services import business_pattern_service as svc


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


# ── Pure function: infer_business_pattern ──────────────────────────────


def _make_pattern(name, industries):
    return BusinessPattern(
        name=name,
        lixinger_industries_json=json.dumps(industries),
        power_tier_baseline=0,
        is_builtin=True,
    )


class TestInferPure:
    def test_unique_match_returns_id(self, db):
        p = _make_pattern("银行", ["银行"])
        db.add(p)
        db.flush()
        result = svc.infer_business_pattern("银行", [p])
        assert result == p.id

    def test_no_industry_returns_none(self, db):
        p = _make_pattern("银行", ["银行"])
        db.add(p)
        db.flush()
        assert svc.infer_business_pattern(None, [p]) is None
        assert svc.infer_business_pattern("", [p]) is None

    def test_no_pattern_covers_returns_none(self, db):
        p = _make_pattern("银行", ["银行"])
        db.add(p)
        db.flush()
        assert svc.infer_business_pattern("未知行业", [p]) is None

    def test_multiple_patterns_cover_returns_none(self, db):
        """1:多 ambiguous → None (force manual)."""
        p1 = _make_pattern("煤化工", ["煤炭开采"])
        p2 = _make_pattern("纯煤开采", ["煤炭开采"])
        db.add_all([p1, p2])
        db.flush()
        result = svc.infer_business_pattern("煤炭开采", [p1, p2])
        assert result is None

    def test_pattern_without_industries_skipped(self, db):
        p1 = BusinessPattern(
            name="空", power_tier_baseline=0, is_builtin=True
        )  # no lixinger_industries_json
        p2 = _make_pattern("银行", ["银行"])
        db.add_all([p1, p2])
        db.flush()
        result = svc.infer_business_pattern("银行", [p1, p2])
        assert result == p2.id


# ── DB CRUD ────────────────────────────────────────────────────────────


class TestCRUD:
    def test_create_user_pattern(self, db):
        p = svc.create_pattern(db, name="我的pattern", first_principle_variable="X")
        assert p.id is not None
        assert p.is_builtin is False
        assert p.source_ref is None
        assert p.power_tier_baseline == 0

    def test_create_user_pattern_rejects_source_ref(self, db):
        with pytest.raises(ValueError, match="source_ref is reserved"):
            svc.create_pattern(
                db, name="用户", source_ref="some ref", is_builtin=False
            )

    def test_create_builtin_pattern_with_source_ref(self, db):
        p = svc.create_pattern(
            db, name="银行", source_ref="invest3 §11", is_builtin=True
        )
        assert p.source_ref == "invest3 §11"

    def test_update_builtin_only_description(self, db):
        p = svc.create_pattern(
            db,
            name="银行",
            first_principle_variable="原始",
            power_tier_baseline=1,
            is_builtin=True,
        )
        # description editable
        updated = svc.update_pattern(db, p.id, description="新描述")
        assert updated.description == "新描述"
        # other fields rejected
        with pytest.raises(ValueError, match="read-only"):
            svc.update_pattern(db, p.id, first_principle_variable="试图修改")
        with pytest.raises(ValueError, match="read-only"):
            svc.update_pattern(db, p.id, power_tier_baseline=3)

    def test_update_user_pattern_all_fields(self, db):
        p = svc.create_pattern(db, name="用户pattern")
        svc.update_pattern(
            db,
            p.id,
            name="新名字",
            first_principle_variable="新核心",
            power_tier_baseline=3,
            description="描述",
        )
        refreshed = svc.get_pattern(db, p.id)
        assert refreshed.name == "新名字"
        assert refreshed.first_principle_variable == "新核心"
        assert refreshed.power_tier_baseline == 3

    def test_delete_user_pattern_clears_stock_refs(self, db):
        p = svc.create_pattern(db, name="待删")
        stock = Stock(code="600001", name="X")
        stock.business_pattern_id = p.id
        db.add(stock)
        db.flush()

        assert svc.delete_pattern(db, p.id) is True
        db.flush()
        # Stock reference cleared — expire to bypass in-memory cache
        db.expire_all()
        refreshed = db.get(Stock, "600001")
        assert refreshed.business_pattern_id is None
        assert refreshed.business_pattern_inferred_at is None
        # Pattern gone
        assert svc.get_pattern(db, p.id) is None

    def test_delete_builtin_refused(self, db):
        p = svc.create_pattern(db, name="银行", is_builtin=True)
        with pytest.raises(ValueError, match="Builtin patterns cannot be deleted"):
            svc.delete_pattern(db, p.id)


# ── Stock inference (DB-bound) ─────────────────────────────────────────


class TestStockInference:
    def test_infer_for_stock_unique_match(self, db):
        p = svc.create_pattern(
            db, name="银行", lixinger_industries=["银行"], is_builtin=True
        )
        stock = Stock(code="600036", name="招商银行", industry="银行")
        db.add(stock)
        db.flush()

        result = svc.infer_for_stock(db, "600036")
        assert result == p.id
        refreshed = db.get(Stock, "600036")
        assert refreshed.business_pattern_id == p.id
        assert refreshed.business_pattern_inferred_at is not None

    def test_infer_for_stock_ambiguous_leaves_null(self, db):
        p1 = svc.create_pattern(
            db, name="煤化工", lixinger_industries=["煤炭"], is_builtin=True
        )
        p2 = svc.create_pattern(
            db, name="纯煤开采", lixinger_industries=["煤炭"], is_builtin=True
        )
        stock = Stock(code="601225", name="陕西煤业", industry="煤炭")
        db.add(stock)
        db.flush()

        result = svc.infer_for_stock(db, "601225")
        assert result is None
        refreshed = db.get(Stock, "601225")
        assert refreshed.business_pattern_id is None

    def test_user_override_protected(self, db):
        """Stock with manual override (inferred_at=None, id set) is protected."""
        p1 = svc.create_pattern(
            db, name="银行", lixinger_industries=["银行"], is_builtin=True
        )
        p2 = svc.create_pattern(
            db, name="煤炭", lixinger_industries=["煤炭"], is_builtin=True
        )
        stock = Stock(code="600036", name="X", industry="银行")
        # Manually override to 煤炭 (mismatched industry)
        stock.business_pattern_id = p2.id
        stock.business_pattern_inferred_at = None  # NULL = override
        db.add(stock)
        db.flush()

        result = svc.infer_for_stock(db, "600036")
        # Without force: returns the override, not the auto-inferred
        assert result == p2.id
        refreshed = db.get(Stock, "600036")
        assert refreshed.business_pattern_id == p2.id
        assert refreshed.business_pattern_inferred_at is None

    def test_infer_for_stock_force_overrides_user_override(self, db):
        p1 = svc.create_pattern(
            db, name="银行", lixinger_industries=["银行"], is_builtin=True
        )
        stock = Stock(code="600036", name="X", industry="银行")
        stock.business_pattern_id = None  # but mark as override somehow
        stock.business_pattern_inferred_at = None
        db.add(stock)
        db.flush()

        # With force=True, inference runs even on NULL-inferred-at
        result = svc.infer_for_stock(db, "600036", force=True)
        assert result == p1.id

    def test_override_stock_pattern(self, db):
        p = svc.create_pattern(
            db, name="银行", lixinger_industries=["银行"], is_builtin=True
        )
        stock = Stock(code="600036", name="X")
        db.add(stock)
        db.flush()

        updated = svc.override_stock_pattern(db, "600036", p.id)
        assert updated.business_pattern_id == p.id
        assert updated.business_pattern_inferred_at is None  # manual = NULL

    def test_override_with_invalid_pattern_id_raises(self, db):
        stock = Stock(code="600036", name="X")
        db.add(stock)
        db.flush()
        with pytest.raises(ValueError, match="does not exist"):
            svc.override_stock_pattern(db, "600036", 99999)

    def test_infer_all_stocks_summary(self, db):
        p = svc.create_pattern(
            db, name="银行", lixinger_industries=["银行"], is_builtin=True
        )
        s1 = Stock(code="600036", name="A", industry="银行")
        s2 = Stock(code="601225", name="B", industry="煤炭")  # no match
        s3 = Stock(code="600000", name="C", industry="银行")
        db.add_all([s1, s2, s3])
        db.flush()

        summary = svc.infer_all_stocks(db)
        assert summary["total"] == 3
        assert summary["updated"] >= 2  # 2 banks matched
        assert summary["protected"] == 0
