"""Test one-shot migration of legacy Holding rows into trades."""
from datetime import date, datetime
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.holding import Holding
from app.models.stock import Stock
from app.models.trade import Trade
from app.models.cash_balance import CashBalance
from app.services.migrations.holding_to_trades_migrator import (
    migrate_holdings_to_trades, MIGRATION_BATCH_ID,
)
from app.services.holding_view_service import get_holding_view


# ---------------------------------------------------------------------------
# Fixtures — local in-memory SQLite (matches test_trade_service convention)
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


@pytest.fixture
def setup(db_session):
    db_session.add(Stock(code="600519", name="贵州茅台", exchange="sh"))
    db_session.add(Stock(code="000001", name="平安银行", exchange="sz"))
    db_session.add(CashBalance(id=1, balance=0.0))
    db_session.flush()


def test_migrate_open_holding(db_session, setup):
    """Open holding (sell_date IS NULL) -> 1 trade."""
    db_session.add(Holding(
        stock_code="600519", buy_date=date(2026, 1, 15),
        buy_price=1680.0, quantity=100, stop_profit_price=2184.0,
    ))
    db_session.flush()
    count = migrate_holdings_to_trades(db_session)
    assert count == 1

    trades = db_session.query(Trade).all()
    assert len(trades) == 1
    t = trades[0]
    assert t.stock_code == "600519"
    assert t.side == "BUY"
    assert t.quantity == 100
    assert t.price == 1680.0
    assert t.filled_at == datetime(2026, 1, 15, 0, 0)
    assert t.commission == 0.0
    assert t.stamp_duty == 0.0
    assert t.transfer_fee == 0.0
    assert t.total_value == 168000.0  # 1680 * 100
    assert t.source == "migration"
    assert t.source_ref == f"{MIGRATION_BATCH_ID}:1"


def test_migrate_skips_closed_holding(db_session, setup):
    """Closed holding (sell_date present) -> skip."""
    db_session.add(Holding(
        stock_code="600519", buy_date=date(2025, 1, 15),
        buy_price=1680.0, quantity=100, stop_profit_price=2184.0,
        sell_date=date(2026, 3, 1), sell_price=1800.0,
    ))
    db_session.flush()
    count = migrate_holdings_to_trades(db_session)
    assert count == 0
    assert db_session.query(Trade).count() == 0


def test_migrate_multiple_holdings(db_session, setup):
    db_session.add(Holding(
        stock_code="600519", buy_date=date(2026, 1, 15),
        buy_price=1680.0, quantity=100, stop_profit_price=2184.0,
    ))
    db_session.add(Holding(
        stock_code="000001", buy_date=date(2026, 2, 1),
        buy_price=15.0, quantity=1000, stop_profit_price=20.0,
    ))
    db_session.flush()
    count = migrate_holdings_to_trades(db_session)
    assert count == 2


def test_migrate_idempotent(db_session, setup):
    """Running twice does not duplicate."""
    db_session.add(Holding(
        stock_code="600519", buy_date=date(2026, 1, 15),
        buy_price=1680.0, quantity=100, stop_profit_price=2184.0,
    ))
    db_session.flush()
    migrate_holdings_to_trades(db_session)
    db_session.commit()
    count2 = migrate_holdings_to_trades(db_session)
    assert count2 == 0
    assert db_session.query(Trade).count() == 1


def test_migrate_updates_cash_balance(db_session, setup):
    """Migration should reduce cash_balance by sum of total_value."""
    db_session.add(Holding(
        stock_code="600519", buy_date=date(2026, 1, 15),
        buy_price=1680.0, quantity=100, stop_profit_price=2184.0,
    ))
    db_session.flush()
    migrate_holdings_to_trades(db_session)
    cb = db_session.query(CashBalance).first()
    # balance starts at 0, minus 168000 = -168000
    assert cb.balance == -168000.0
    assert cb.last_trade_id is not None


def test_migrated_holding_appears_in_holding_view(db_session, setup):
    """After migration, holding_view_service should show the position."""
    db_session.add(Holding(
        stock_code="600519", buy_date=date(2026, 1, 15),
        buy_price=1680.0, quantity=100, stop_profit_price=2184.0,
    ))
    db_session.flush()
    migrate_holdings_to_trades(db_session)
    holdings = get_holding_view(db_session)
    assert len(holdings) == 1
    assert holdings[0]["stock_code"] == "600519"
    assert holdings[0]["total_quantity"] == 100


def test_migrate_preserves_buy_date_as_filled_at(db_session, setup):
    db_session.add(Holding(
        stock_code="600519", buy_date=date(2025, 7, 23),
        buy_price=1500.0, quantity=200, stop_profit_price=2000.0,
    ))
    db_session.flush()
    migrate_holdings_to_trades(db_session)
    t = db_session.query(Trade).first()
    assert t.filled_at == datetime(2025, 7, 23, 0, 0)
