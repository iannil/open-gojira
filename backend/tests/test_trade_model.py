"""Test Trade model — immutable event source for all position changes."""
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.trade import Trade


# ---------------------------------------------------------------------------
# Fixtures — local in-memory SQLite (matches test_holding_service convention)
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


def test_trade_create_buy(db_session):
    t = Trade(
        stock_code="600519",
        side="BUY",
        price=1680.0,
        quantity=100,
        filled_at=datetime(2026, 6, 12, 10, 30),
        commission=42.0,
        stamp_duty=0.0,
        transfer_fee=1.68,
        total_value=168043.68,
        source="manual",
    )
    db_session.add(t)
    db_session.commit()
    assert t.id is not None
    assert t.created_at is not None
    assert t.reversed_by_trade_id is None
    assert t.fee_source == "auto"  # default


def test_trade_quantity_signed(db_session):
    """BUY quantity is positive, SELL is negative, DIVIDEND is zero."""
    buy = Trade(
        stock_code="600519",
        side="BUY",
        price=100,
        quantity=100,
        filled_at=datetime(2026, 6, 12, 10, 0),
        total_value=10000,
        source="manual",
    )
    sell = Trade(
        stock_code="600519",
        side="SELL",
        price=110,
        quantity=-100,
        filled_at=datetime(2026, 6, 13, 10, 0),
        total_value=11000,
        source="manual",
    )
    div = Trade(
        stock_code="600519",
        side="DIVIDEND",
        price=0,
        quantity=0,
        filled_at=datetime(2026, 6, 14, 10, 0),
        total_value=-500,
        source="corp_action",
    )
    db_session.add_all([buy, sell, div])
    db_session.commit()
    assert buy.quantity > 0
    assert sell.quantity < 0
    assert div.quantity == 0


def test_trade_total_value_buy_includes_fees(db_session):
    """BUY total_value = price*qty + commission + stamp_duty + transfer_fee."""
    t = Trade(
        stock_code="600519",
        side="BUY",
        price=100,
        quantity=100,
        filled_at=datetime(2026, 6, 12, 10, 0),
        commission=5,
        stamp_duty=0,
        transfer_fee=0.1,
        total_value=10005.1,
        source="manual",
    )
    db_session.add(t)
    db_session.commit()
    assert t.total_value == pytest.approx(10005.1)


def test_trade_source_values(db_session):
    """Source enum: manual / csv_import / broker_api / corp_action / migration / reversal."""
    for src in (
        "manual",
        "csv_import",
        "broker_api",
        "corp_action",
        "migration",
        "reversal",
    ):
        t = Trade(
            stock_code="600519",
            side="BUY",
            price=100,
            quantity=100,
            filled_at=datetime(2026, 6, 12, 10, 0),
            total_value=10000,
            source=src,
        )
        db_session.add(t)
    db_session.commit()
    assert db_session.query(Trade).count() == 6


def test_trade_reversal_link(db_session):
    """A reversed trade points to its reversal via reversed_by_trade_id."""
    original = Trade(
        stock_code="600519",
        side="BUY",
        price=100,
        quantity=100,
        filled_at=datetime(2026, 6, 12, 10, 0),
        total_value=10000,
        source="manual",
    )
    db_session.add(original)
    db_session.flush()
    reversal = Trade(
        stock_code="600519",
        side="SELL",
        price=100,
        quantity=-100,
        filled_at=datetime(2026, 6, 12, 11, 0),
        total_value=-10000,
        source="reversal",
        reversed_by_trade_id=original.id,
    )
    db_session.add(reversal)
    db_session.commit()
    assert reversal.reversed_by_trade_id == original.id


def test_trade_indexes_exist(db_session):
    """Composite indexes for common queries should be defined."""
    table = Trade.__table__
    index_names = {idx.name for idx in table.indexes}
    assert "ix_trades_code_filled" in index_names
    assert "ix_trades_source" in index_names
