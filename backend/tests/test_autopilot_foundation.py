"""Step 1 (autopilot foundation): cashflow_goal singleton + audit_log +
stocks.quadrant column.

Service-level tests follow the project convention (see tests/test_bank_profile.py
etc.) — TestSessionLocal directly, no HTTP layer. The router code is a thin
shim over the service.
"""

import json

import pytest

from app.models.stock import Stock
from app.routers.cashflow_goal import _to_response as cashflow_to_response
from app.schemas.cashflow_goal import CashflowGoalUpdate
from app.services import audit_log_service, cashflow_goal_service
from tests.conftest import TestSessionLocal


@pytest.fixture
def db():
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


# ── stocks.quadrant column ─────────────────────────────────────────────
def test_stock_quadrant_column_round_trips(db):
    db.add(
        Stock(
            code="601398",
            name="工商银行",
            industry="银行",
            quadrant="financial",
        )
    )
    db.commit()
    row = db.query(Stock).filter(Stock.code == "601398").one()
    assert row.quadrant == "financial"


def test_stock_quadrant_defaults_to_null(db):
    db.add(Stock(code="600519", name="贵州茅台", industry="白酒"))
    db.commit()
    row = db.query(Stock).filter(Stock.code == "600519").one()
    assert row.quadrant is None


# ── cashflow-goal service ──────────────────────────────────────────────
def test_cashflow_goal_get_or_create_is_singleton(db):
    a = cashflow_goal_service.get_or_create(db)
    b = cashflow_goal_service.get_or_create(db)
    assert a.id == 1 and b.id == 1
    assert a.annual_expense == 0.0
    assert a.goal_multiple == 15.0
    assert a.currency == "CNY"


def test_cashflow_goal_target_annual_cashflow_formula(db):
    goal = cashflow_goal_service.update(db, annual_expense=120_000, goal_multiple=20)
    assert cashflow_goal_service.target_annual_cashflow(goal) == 2_400_000


def test_cashflow_goal_update_partial_keeps_other_fields(db):
    cashflow_goal_service.update(db, annual_expense=200_000)
    cashflow_goal_service.update(db, goal_multiple=12)
    goal = cashflow_goal_service.get_or_create(db)
    assert goal.annual_expense == 200_000
    assert goal.goal_multiple == 12
    assert cashflow_goal_service.target_annual_cashflow(goal) == 2_400_000


def test_cashflow_goal_update_persists_notes_and_currency(db):
    cashflow_goal_service.update(
        db, annual_expense=180_000, notes="FIRE 计划", currency="HKD"
    )
    goal = cashflow_goal_service.get_or_create(db)
    assert goal.notes == "FIRE 计划"
    assert goal.currency == "HKD"


def test_cashflow_goal_response_shape(db):
    goal = cashflow_goal_service.update(db, annual_expense=150_000, goal_multiple=18)
    resp = cashflow_to_response(goal)
    assert resp.annual_expense == 150_000
    assert resp.goal_multiple == 18
    assert resp.target_annual_cashflow == 150_000 * 18
    assert resp.currency == "CNY"


# ── pydantic schema validation ─────────────────────────────────────────
def test_cashflow_goal_update_rejects_negative_expense():
    with pytest.raises(ValueError):
        CashflowGoalUpdate(annual_expense=-1)


def test_cashflow_goal_update_rejects_non_positive_multiple():
    with pytest.raises(ValueError):
        CashflowGoalUpdate(goal_multiple=0)


# ── audit_log service ──────────────────────────────────────────────────
def test_audit_log_write_persists_all_fields(db):
    audit_log_service.write(
        db,
        entity_type="plan",
        entity_id="P-1",
        event="created",
        actor="user",
        stock_code="601398",
        summary="新建预案",
        payload={"version": 1, "thesis": "盲盒可视化"},
    )
    db.commit()
    rows = audit_log_service.recent(db)
    assert len(rows) == 1
    row = rows[0]
    assert row.entity_type == "plan"
    assert row.entity_id == "P-1"
    assert row.event == "created"
    assert row.actor == "user"
    assert row.stock_code == "601398"
    assert row.summary == "新建预案"
    assert json.loads(row.payload)["version"] == 1


def test_audit_log_recent_filters_by_entity_type(db):
    audit_log_service.write(db, entity_type="plan", event="created", summary="a")
    audit_log_service.write(db, entity_type="draft", event="created", summary="b")
    audit_log_service.write(db, entity_type="plan", event="updated", summary="c")
    db.commit()
    plan_rows = audit_log_service.recent(db, entity_type="plan")
    assert {r.summary for r in plan_rows} == {"a", "c"}
    draft_rows = audit_log_service.recent(db, entity_type="draft")
    assert len(draft_rows) == 1


def test_audit_log_recent_filters_by_stock_and_event(db):
    audit_log_service.write(
        db, entity_type="plan", event="created", stock_code="601398", summary="a"
    )
    audit_log_service.write(
        db, entity_type="plan", event="invalidated", stock_code="601398", summary="b"
    )
    audit_log_service.write(
        db, entity_type="plan", event="created", stock_code="600519", summary="c"
    )
    db.commit()
    assert len(audit_log_service.recent(db, stock_code="601398")) == 2
    assert len(audit_log_service.recent(db, event="invalidated")) == 1


def test_audit_log_summary_truncated_to_500_chars(db):
    audit_log_service.write(
        db, entity_type="plan", event="x", summary="A" * 1000
    )
    db.commit()
    row = audit_log_service.recent(db)[0]
    assert len(row.summary) == 500


def test_audit_log_payload_optional(db):
    audit_log_service.write(db, entity_type="plan", event="x", summary="s")
    db.commit()
    row = audit_log_service.recent(db)[0]
    assert row.payload is None


def test_audit_log_actor_defaults_to_system(db):
    audit_log_service.write(db, entity_type="plan", event="x", summary="s")
    db.commit()
    row = audit_log_service.recent(db)[0]
    assert row.actor == "system"


def test_audit_log_recent_orders_by_created_desc(db):
    for i in range(5):
        audit_log_service.write(
            db, entity_type="plan", event="x", summary=f"row-{i}"
        )
    db.commit()
    rows = audit_log_service.recent(db, limit=3)
    assert len(rows) == 3
    # newest first → row-4 leads
    assert rows[0].summary == "row-4"


# ── Alembic migration sanity ───────────────────────────────────────────
def test_alembic_step1_revision_exists_in_chain():
    """Step 1's revision must remain part of the linear migration chain."""
    from pathlib import Path

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    project_root = Path(__file__).resolve().parents[1]
    cfg = Config(str(project_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(project_root / "alembic"))
    script_dir = ScriptDirectory.from_config(cfg)
    revisions = {r.revision for r in script_dir.walk_revisions()}
    assert "h8c9d0e1f2g3" in revisions
    heads = script_dir.get_heads()
    assert len(heads) == 1, f"expected single head, got {heads}"


def test_alembic_migration_creates_expected_objects(tmp_path, monkeypatch):
    """Verify the new revision's upgrade() actually creates the right objects.

    We stamp to the revision just before our new one (n4o5p6q7r8s9),
    set up a DB with the old plans schema, then run only our migration.
    """
    from pathlib import Path

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    from app import config as app_config
    from app.db.base import Base

    project_root = Path(__file__).resolve().parents[1]
    db_file = tmp_path / "alembic_test.db"
    tmp_url = f"sqlite:///{db_file}"
    monkeypatch.setattr(app_config.settings, "DATABASE_URL", tmp_url)

    # Create baseline with all models, then manipulate to simulate
    # the state just before the strategy_driven_screening_system migration.
    engine = create_engine(tmp_url)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        # Drop new tables so the migration creates them
        conn.exec_driver_sql("DROP TABLE IF EXISTS candidates")
        conn.exec_driver_sql("DROP TABLE IF EXISTS strategies")
        # Recreate plans with old schema (the migration will rebuild it)
        conn.exec_driver_sql("DROP TABLE IF EXISTS plans")
        conn.exec_driver_sql("""
            CREATE TABLE plans (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                code VARCHAR NOT NULL,
                version INTEGER NOT NULL,
                status VARCHAR NOT NULL,
                thesis VARCHAR NOT NULL,
                effective_from DATE NOT NULL,
                effective_until DATE NOT NULL,
                spec_json VARCHAR NOT NULL,
                theme_id INTEGER,
                created_at DATETIME,
                updated_at DATETIME,
                FOREIGN KEY(code) REFERENCES stocks (code)
            )
        """)

    cfg = Config(str(project_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(project_root / "alembic"))
    # Stamp to revision just before ours
    command.stamp(cfg, "n4o5p6q7r8s9")
    # Run only our migration
    command.upgrade(cfg, "3c5b80889c29")

    insp = inspect(engine)
    tables = set(insp.get_table_names())
    assert "strategies" in tables
    assert "candidates" in tables
    plans_cols = {c["name"] for c in insp.get_columns("plans")}
    assert "slug" in plans_cols
    assert "strategy_composition_json" in plans_cols
    assert "code" not in plans_cols
    assert "version" not in plans_cols
