"""Test holding_view_service — derive holdings from trades."""
from datetime import datetime, date, timedelta
import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.services.trade_service import record_trade
from app.services.holding_view_service import (
    get_holding_view, available_quantity_at, frozen_quantity_at,
)
from app.models.cash_balance import CashBalance
from app.models.broker_fee_config import BrokerFeeConfig
from app.models.stock import Stock


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
    db_session.add(CashBalance(id=1, balance=1000000.0))
    db_session.add(BrokerFeeConfig(
        broker_name="default", commission_rate=0.00025, commission_min=5.0,
        stamp_duty_rate=0.0005, transfer_fee_rate=0.00001,
        effective_from=date(2023, 10, 23), is_active=True,
    ))
    db_session.flush()


def test_empty_holdings(db_session, setup):
    assert get_holding_view(db_session) == []


def test_single_buy(db_session, setup):
    record_trade(db_session, stock_code="600519", side="BUY",
                 price=100.0, quantity=200,
                 filled_at=datetime(2026, 6, 11, 10, 0), source="manual")
    holdings = get_holding_view(db_session)
    assert len(holdings) == 1
    h = holdings[0]
    assert h["stock_code"] == "600519"
    assert h["total_quantity"] == 200
    # avg_cost_basis ≈ (100×200 + fees) / 200 ≈ 100.025 (rough)
    assert 99 < h["avg_cost_basis"] < 101


def test_avg_cost_after_multiple_buys(db_session, setup):
    record_trade(db_session, stock_code="600519", side="BUY",
                 price=100.0, quantity=100,
                 filled_at=datetime(2026, 6, 10, 10, 0), source="manual")
    record_trade(db_session, stock_code="600519", side="BUY",
                 price=120.0, quantity=100,
                 filled_at=datetime(2026, 6, 11, 10, 0), source="manual")
    holdings = get_holding_view(db_session)
    h = holdings[0]
    assert h["total_quantity"] == 200
    # weighted avg = (10000ish + 12000ish) / 200
    assert 100 < h["avg_cost_basis"] < 120


def test_partial_sell_reduces_quantity(db_session, setup):
    record_trade(db_session, stock_code="600519", side="BUY",
                 price=100.0, quantity=200,
                 filled_at=datetime(2026, 6, 10, 10, 0), source="manual")
    record_trade(db_session, stock_code="600519", side="SELL",
                 price=110.0, quantity=100,
                 filled_at=datetime(2026, 6, 12, 10, 0), source="manual")
    holdings = get_holding_view(db_session)
    assert holdings[0]["total_quantity"] == 100  # 200 - 100


def test_fully_closed_position_excluded(db_session, setup):
    """Position with quantity <= 0 should not appear."""
    record_trade(db_session, stock_code="600519", side="BUY",
                 price=100.0, quantity=100,
                 filled_at=datetime(2026, 6, 10, 10, 0), source="manual")
    record_trade(db_session, stock_code="600519", side="SELL",
                 price=110.0, quantity=100,
                 filled_at=datetime(2026, 6, 12, 10, 0), source="manual")
    holdings = get_holding_view(db_session)
    assert holdings == []


def test_multiple_stocks(db_session, setup):
    record_trade(db_session, stock_code="600519", side="BUY",
                 price=100.0, quantity=100,
                 filled_at=datetime(2026, 6, 10, 10, 0), source="manual")
    record_trade(db_session, stock_code="000001", side="BUY",
                 price=15.0, quantity=1000,
                 filled_at=datetime(2026, 6, 10, 10, 0), source="manual")
    holdings = get_holding_view(db_session)
    assert len(holdings) == 2
    codes = {h["stock_code"] for h in holdings}
    assert codes == {"600519", "000001"}


def test_first_and_last_trade_at(db_session, setup):
    record_trade(db_session, stock_code="600519", side="BUY",
                 price=100.0, quantity=100,
                 filled_at=datetime(2026, 6, 10, 10, 0), source="manual")
    record_trade(db_session, stock_code="600519", side="BUY",
                 price=110.0, quantity=100,
                 filled_at=datetime(2026, 6, 11, 14, 0), source="manual")
    h = get_holding_view(db_session)[0]
    assert h["first_buy_at"] == datetime(2026, 6, 10, 10, 0)
    assert h["last_trade_at"] == datetime(2026, 6, 11, 14, 0)


def test_available_quantity_excludes_today_buy(db_session, setup):
    """T+1: shares bought today are frozen."""
    # 昨天 buy 100,今日 buy 100
    record_trade(db_session, stock_code="600519", side="BUY",
                 price=100.0, quantity=100,
                 filled_at=datetime(2026, 6, 11, 10, 0), source="manual")
    record_trade(db_session, stock_code="600519", side="BUY",
                 price=110.0, quantity=100,
                 filled_at=datetime(2026, 6, 12, 10, 0), source="manual")  # today
    # 在今日 14:00 查 available
    avail = available_quantity_at(db_session, "600519", datetime(2026, 6, 12, 14, 0))
    assert avail == 100  # only yesterday's
    frozen = frozen_quantity_at(db_session, "600519", datetime(2026, 6, 12, 14, 0))
    assert frozen == 100


def test_available_quantity_after_sell(db_session, setup):
    record_trade(db_session, stock_code="600519", side="BUY",
                 price=100.0, quantity=200,
                 filled_at=datetime(2026, 6, 10, 10, 0), source="manual")
    record_trade(db_session, stock_code="600519", side="SELL",
                 price=110.0, quantity=80,
                 filled_at=datetime(2026, 6, 11, 10, 0), source="manual")
    avail = available_quantity_at(db_session, "600519", datetime(2026, 6, 11, 14, 0))
    assert avail == 120  # 200 - 80


def test_available_quantity_next_day_unfreezes(db_session, setup):
    """Today's buys become available tomorrow."""
    record_trade(db_session, stock_code="600519", side="BUY",
                 price=100.0, quantity=100,
                 filled_at=datetime(2026, 6, 12, 10, 0), source="manual")
    # 查明日
    avail = available_quantity_at(db_session, "600519", datetime(2026, 6, 13, 10, 0))
    assert avail == 100


def test_as_of_filter(db_session, setup):
    """as_of parameter should restrict to trades filled before that time."""
    record_trade(db_session, stock_code="600519", side="BUY",
                 price=100.0, quantity=100,
                 filled_at=datetime(2026, 6, 10, 10, 0), source="manual")
    record_trade(db_session, stock_code="600519", side="BUY",
                 price=120.0, quantity=100,
                 filled_at=datetime(2026, 6, 12, 10, 0), source="manual")
    # 在 6 月 11 日查(只看到 6/10 的)
    holdings = get_holding_view(db_session, as_of=datetime(2026, 6, 11, 10, 0))
    assert len(holdings) == 1
    assert holdings[0]["total_quantity"] == 100


def test_reversed_trade_excluded(db_session, setup):
    """Trades with reversed_by_trade_id set should not count."""
    from app.models.trade import Trade
    record_trade(db_session, stock_code="600519", side="BUY",
                 price=100.0, quantity=100,
                 filled_at=datetime(2026, 6, 10, 10, 0), source="manual")
    # 标记为已红冲
    t = db_session.query(Trade).first()
    t.reversed_by_trade_id = t.id  # self-reference for test simplicity
    db_session.flush()
    holdings = get_holding_view(db_session)
    # trade 被排除,所以持仓为空
    # 但 t.id == t.reversed_by_trade_id 自引用可能不被排除(看实现)
    # 测试意图:有 reversed_by_trade_id 的不参与计算
    assert holdings == []
