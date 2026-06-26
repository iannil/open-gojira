"""position_service — derive holdings/P&L from the Trade ledger (event sourcing).

Trades are the single source of truth (decision Q2-A, 2026-06-26 paper-trading
loop design). Positions, cost basis (moving weighted average), realized and
unrealized P&L are all derived from the immutable Trade rows.

Trade.quantity is signed: +N BUY, -N SELL, 0 DIVIDEND, +/-N CORP_ACTION.
Trade.total_value: BUY = notional + fees (cash out); SELL = notional - fees (cash in).
"""
from datetime import date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.trade import Trade


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    import app.models  # noqa: F401 — register all ORM tables
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _trade(db, code, side, price, qty, total_value, *, when, source="manual", source_ref=None):
    """Insert a Trade row with the real signed-quantity convention."""
    signed = {"BUY": qty, "SELL": -qty, "DIVIDEND": 0, "CORP_ACTION": qty}[side]
    t = Trade(
        stock_code=code,
        side=side,
        price=price,
        quantity=signed,
        filled_at=when,
        total_value=total_value,
        source=source,
        source_ref=source_ref,
    )
    db.add(t)
    db.flush()
    return t


def test_single_buy_position(db_session):
    """One BUY → quantity and avg_cost (cost basis includes buy fees)."""
    from app.services.position_service import position_for

    _trade(db_session, "600519", "BUY", price=100.0, qty=100, total_value=10042.0,
           when=datetime(2026, 6, 12, 10, 0))

    pos = position_for(db_session, "600519", price_lookup=lambda c: None)
    assert pos is not None
    assert pos.quantity == 100
    assert pos.avg_cost == pytest.approx(100.42)   # 10042 / 100, fees folded in
    assert pos.cost_basis == pytest.approx(10042.0)
    assert pos.realized_pnl == pytest.approx(0.0)


def test_buy_then_partial_sell(db_session):
    """SELL realizes P&L against the running average; remaining qty/cost shrink."""
    from app.services.position_service import position_for

    _trade(db_session, "600519", "BUY", price=100.0, qty=100, total_value=10042.0,
           when=datetime(2026, 6, 12, 10, 0))
    # Sell 40 @ 110 → net proceeds 4380 (notional 4400 − 20 fees).
    _trade(db_session, "600519", "SELL", price=110.0, qty=40, total_value=4380.0,
           when=datetime(2026, 6, 15, 10, 0))

    pos = position_for(db_session, "600519", price_lookup=lambda c: None)
    assert pos.quantity == 60
    assert pos.avg_cost == pytest.approx(100.42)           # unchanged by sell
    assert pos.cost_basis == pytest.approx(6025.2)         # 10042 − 100.42×40
    # realized = 4380 − 100.42×40 = 363.2
    assert pos.realized_pnl == pytest.approx(363.2)


def test_moving_average_not_fifo(db_session):
    """Realized P&L uses the running average, not first-in cost (distinguishes
    moving-average from FIFO)."""
    from app.services.position_service import position_for

    _trade(db_session, "600519", "BUY", price=100.0, qty=100, total_value=10000.0,
           when=datetime(2026, 6, 10, 10, 0))
    _trade(db_session, "600519", "BUY", price=200.0, qty=100, total_value=20000.0,
           when=datetime(2026, 6, 11, 10, 0))
    # avg now 150. Sell 100 @ 160 → net 16000.
    _trade(db_session, "600519", "SELL", price=160.0, qty=100, total_value=16000.0,
           when=datetime(2026, 6, 12, 10, 0))

    pos = position_for(db_session, "600519", price_lookup=lambda c: None)
    assert pos.quantity == 100
    assert pos.avg_cost == pytest.approx(150.0)
    # moving-avg realized = 16000 − 150×100 = 1000 (FIFO would be 6000)
    assert pos.realized_pnl == pytest.approx(1000.0)
    assert pos.cost_basis == pytest.approx(15000.0)


def test_full_sell_closes_position(db_session):
    """Selling the whole position → qty 0, excluded from current_positions,
    but realized P&L is still derivable via position_for."""
    from app.services.position_service import current_positions, position_for

    _trade(db_session, "600519", "BUY", price=100.0, qty=100, total_value=10000.0,
           when=datetime(2026, 6, 10, 10, 0))
    _trade(db_session, "600519", "SELL", price=120.0, qty=100, total_value=12000.0,
           when=datetime(2026, 6, 12, 10, 0))

    pos = position_for(db_session, "600519", price_lookup=lambda c: None)
    assert pos.quantity == 0
    assert pos.cost_basis == pytest.approx(0.0)
    assert pos.realized_pnl == pytest.approx(2000.0)

    assert [p.stock_code for p in current_positions(db_session)] == []


def test_available_quantity_excludes_same_day_buys(db_session):
    """T+1: shares bought on the query date are frozen and not sellable today."""
    from app.services.position_service import available_quantity

    _trade(db_session, "600519", "BUY", price=100.0, qty=100, total_value=10000.0,
           when=datetime(2026, 6, 12, 10, 0))
    _trade(db_session, "600519", "BUY", price=100.0, qty=50, total_value=5000.0,
           when=datetime(2026, 6, 15, 9, 40))

    # On 6-15, the 50 bought today are frozen → only 100 sellable.
    assert available_quantity(db_session, "600519", date(2026, 6, 15)) == 100
    # On 6-16, all 150 are settled.
    assert available_quantity(db_session, "600519", date(2026, 6, 16)) == 150


def test_corp_action_stock_dividend_dilutes_avg_cost(db_session):
    """Stock dividend (送股): free shares raise quantity, leave book cost
    unchanged, so the average cost is diluted down."""
    from app.services.position_service import position_for

    _trade(db_session, "600519", "BUY", price=100.0, qty=100, total_value=10000.0,
           when=datetime(2026, 6, 10, 10, 0))
    # 10-for-100 stock dividend: +10 shares at price 0, no cash impact.
    _trade(db_session, "600519", "CORP_ACTION", price=0.0, qty=10, total_value=0.0,
           when=datetime(2026, 6, 20, 10, 0))

    pos = position_for(db_session, "600519", price_lookup=lambda c: None)
    assert pos.quantity == 110
    assert pos.cost_basis == pytest.approx(10000.0)        # unchanged
    assert pos.avg_cost == pytest.approx(10000.0 / 110)    # diluted


def test_current_positions_multi_stock(db_session):
    """current_positions returns every open stock and omits closed ones."""
    from app.services.position_service import current_positions

    _trade(db_session, "600519", "BUY", price=100.0, qty=100, total_value=10000.0,
           when=datetime(2026, 6, 10, 10, 0))
    _trade(db_session, "000001", "BUY", price=10.0, qty=200, total_value=2000.0,
           when=datetime(2026, 6, 10, 10, 0))
    # 600036 opened then fully closed → must not appear.
    _trade(db_session, "600036", "BUY", price=40.0, qty=50, total_value=2000.0,
           when=datetime(2026, 6, 10, 10, 0))
    _trade(db_session, "600036", "SELL", price=45.0, qty=50, total_value=2250.0,
           when=datetime(2026, 6, 12, 10, 0))

    codes = {p.stock_code for p in current_positions(db_session, price_lookup=lambda c: None)}
    assert codes == {"600519", "000001"}


def test_unrealized_pnl_with_injected_price(db_session):
    """Unrealized P&L = (current_price − avg_cost) × qty, via injected lookup."""
    from app.services.position_service import position_for

    _trade(db_session, "600519", "BUY", price=100.0, qty=100, total_value=10000.0,
           when=datetime(2026, 6, 10, 10, 0))

    pos = position_for(db_session, "600519", price_lookup=lambda code: 120.0)
    assert pos.unrealized_pnl == pytest.approx(2000.0)   # (120 − 100) × 100

    # No price available → unrealized stays 0 (cannot be computed).
    pos_noprice = position_for(db_session, "600519", price_lookup=lambda code: None)
    assert pos_noprice.unrealized_pnl == pytest.approx(0.0)
