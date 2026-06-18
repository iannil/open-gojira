import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, pool
from sqlalchemy.orm import sessionmaker

import app.db.session as _session_module
from app.db.base import Base
from app.db.session import get_db
from app.main import app

TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=pool.StaticPool,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


# F16 (2026-06-18): patch SessionLocal at the module level so any service
# that does `from app.db.session import SessionLocal` then `db = SessionLocal()`
# (research_runner_service / pipeline manager / scheduler jobs / event handlers)
# gets the in-memory test session, not the production SQLite.
# Previously, scheduler jobs and event handlers spawned during tests wrote
# directly to data/gojira.db, polluting the production DB with test fixtures
# (178 audit_logs + 79 system_alerts with "E2E 测试" / "x(601398)" content).
_session_module.SessionLocal = TestSessionLocal


@pytest.fixture(autouse=True)
def setup_db():
    import app.models  # noqa: F401 — register all ORM tables
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db_session():
    """Shared session bound to the same StaticPool in-memory engine that
    ``client`` (via override_get_db) uses.

    Tests that need to seed data outside of HTTP can use this fixture and
    rely on the fact that autoflush will push pending rows before the
    request handler's separate session reads them.
    """
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()
