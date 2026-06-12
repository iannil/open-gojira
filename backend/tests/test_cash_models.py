"""Test cash_balance (singleton) and cash_adjustments (deposit/withdrawal log)."""
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.cash_adjustment import CashAdjustment
from app.models.cash_balance import CashBalance


# ---------------------------------------------------------------------------
# Fixtures — local in-memory SQLite (matches test_trade_model convention)
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session():
    """Create an in-memory SQLite session with all tables."""
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    import app.models  # noqa: F401 — register all ORM tables
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def test_cash_balance_singleton_default(db_session):
    cb = CashBalance(balance=100000.0)
    db_session.add(cb)
    db_session.commit()
    assert cb.id == 1
    assert cb.balance == 100000.0
    assert cb.as_of_at is not None


def test_cash_balance_last_trade_id_nullable(db_session):
    cb = CashBalance(balance=0)
    db_session.add(cb)
    db_session.commit()
    assert cb.last_trade_id is None
    assert cb.last_adjustment_id is None


def test_cash_adjustment_deposit(db_session):
    adj = CashAdjustment(
        amount=50000.0,
        happened_at=datetime(2026, 6, 12, 9, 0),
        reason="deposit",
        note="月度入金",
    )
    db_session.add(adj)
    db_session.commit()
    assert adj.id is not None
    assert adj.created_at is not None


def test_cash_adjustment_withdrawal_negative_amount(db_session):
    adj = CashAdjustment(
        amount=-30000.0,
        happened_at=datetime(2026, 6, 12, 14, 0),
        reason="withdrawal",
        note="应急取现",
    )
    db_session.add(adj)
    db_session.commit()
    assert adj.amount == -30000.0


def test_cash_adjustment_reason_values(db_session):
    """All supported reasons."""
    for i, reason in enumerate(("deposit", "withdrawal", "dividend", "other")):
        db_session.add(
            CashAdjustment(
                amount=100.0 * i,
                happened_at=datetime(2026, 6, 1, 12, 0),
                reason=reason,
            )
        )
    db_session.commit()
    assert db_session.query(CashAdjustment).count() == 4


def test_cash_adjustment_happened_at_indexed(db_session):
    """happened_at should be indexed for range queries."""
    table = CashAdjustment.__table__
    happened_col = table.c.happened_at
    assert happened_col.index
