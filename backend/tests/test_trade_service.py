"""Test trade_service — atomic trade + cash_balance write."""
from datetime import datetime, date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.cash_balance import CashBalance
from app.models.broker_fee_config import BrokerFeeConfig
from app.models.stock import Stock
from app.models.trade import Trade
from app.services.trade_service import (
    record_trade,
    InsufficientBalanceError,
    NoActiveFeeConfigError,
)


def _seed_settled_buy(db, code="600519", quantity=100, buy_price=1680.0, buy_date=date(2026, 6, 11)):
    """Q2-A: sellable quantity is derived from the Trade ledger. Seed a settled
    (prior-day) BUY trade so the shares are T+1-available."""
    db.add(Trade(
        stock_code=code, side="BUY", price=buy_price, quantity=quantity,
        filled_at=datetime(buy_date.year, buy_date.month, buy_date.day, 10, 0),
        total_value=buy_price * quantity, source="manual",
    ))
    db.flush()


# ---------------------------------------------------------------------------
# Fixtures — local in-memory SQLite (matches test_cash_models convention)
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
    """初始 cash 200000 + 一只股票 + 默认费率配置."""
    # prev_close=1680 → price band [1512, 1848] covers all BUY/SELL prices
    # used in this test module (1680 / 1700 / 1000).
    db_session.add(Stock(
        code="600519", name="贵州茅台", exchange="sh",
        listing_status="normally_listed", prev_close=1680.0,
    ))
    db_session.add(CashBalance(id=1, balance=200000.0))
    db_session.add(BrokerFeeConfig(
        broker_name="default",
        commission_rate=0.00025, commission_min=5.0,
        stamp_duty_rate=0.0005, transfer_fee_rate=0.00001,
        effective_from=date(2023, 10, 23), is_active=True,
    ))
    db_session.flush()
    return None


def test_record_buy_creates_trade_and_updates_cash(db_session, setup):
    trade = record_trade(
        db_session,
        stock_code="600519", side="BUY",
        price=1680.0, quantity=100,
        filled_at=datetime(2026, 6, 12, 10, 30),
        source="manual",
    )
    assert trade.id is not None
    assert trade.side == "BUY"
    assert trade.quantity == 100  # BUY quantity positive
    # 168000 + 42 + 0 + 1.68 = 168043.68
    assert trade.total_value == pytest.approx(168043.68, abs=0.01)
    assert trade.commission == 42.0
    assert trade.stamp_duty == 0.0
    assert trade.transfer_fee == pytest.approx(1.68, abs=0.01)

    cb = db_session.query(CashBalance).first()
    assert cb.balance == pytest.approx(200000 - 168043.68, abs=0.01)
    assert cb.last_trade_id == trade.id


def test_record_sell_updates_cash_inflow(db_session, setup):
    # v2: 持仓来自 Holding; BUY 交易记现金支出, SELL 卖出 Holding 头寸
    _seed_settled_buy(db_session, quantity=100, buy_price=1680.0)
    record_trade(db_session, stock_code="600519", side="BUY",
                 price=1680.0, quantity=100,
                 filled_at=datetime(2026, 6, 11, 10, 30), source="manual")
    trade = record_trade(db_session, stock_code="600519", side="SELL",
                         price=1700.0, quantity=100,
                         filled_at=datetime(2026, 6, 12, 10, 30), source="manual")
    assert trade.quantity == -100  # SELL quantity negative
    # SELL: 170000 - 42.5 - 85 - 1.7 = 169870.8
    assert trade.total_value == pytest.approx(169870.80, abs=0.01)
    cb = db_session.query(CashBalance).first()
    # 200000 - 168043.68 + 169870.8
    assert cb.balance == pytest.approx(200000 - 168043.68 + 169870.80, abs=0.5)


def test_buy_exceeding_cash_raises(db_session, setup):
    # cash 200000,试图买 200 股 × 1680 = 336000 notional
    with pytest.raises(InsufficientBalanceError):
        record_trade(db_session, stock_code="600519", side="BUY",
                     price=1680.0, quantity=200,
                     filled_at=datetime(2026, 6, 12, 10, 30), source="manual")


def test_no_active_fee_config_raises(db_session):
    """No broker_fee_config in DB → raise NoActiveFeeConfigError."""
    db_session.add(Stock(
        code="600519", name="贵州茅台", exchange="sh",
        listing_status="normally_listed", prev_close=100.0,
    ))
    db_session.add(CashBalance(id=1, balance=100000.0))
    db_session.flush()
    with pytest.raises(NoActiveFeeConfigError):
        record_trade(db_session, stock_code="600519", side="BUY",
                     price=100.0, quantity=10,
                     filled_at=datetime(2026, 6, 12, 10, 0), source="manual")


def test_cash_balance_auto_created_if_missing(db_session, setup):
    """If cash_balance singleton row absent, create it with 0 balance."""
    # 删除 setup 创建的 cash_balance
    db_session.query(CashBalance).delete()
    db_session.flush()
    # 现在 trade 会自动建一个 balance=0 的 singleton
    # 试图买任何东西都会 InsufficientBalanceError(balance=0)
    with pytest.raises(InsufficientBalanceError):
        record_trade(db_session, stock_code="600519", side="BUY",
                     price=1680.0, quantity=10,
                     filled_at=datetime(2026, 6, 12, 10, 0), source="manual")


def test_commission_override(db_session, setup):
    """User can override auto-computed commission (e.g. broker min kicked in differently)."""
    trade = record_trade(
        db_session, stock_code="600519", side="BUY",
        price=1680.0, quantity=100,
        filled_at=datetime(2026, 6, 12, 10, 30),
        source="manual", commission_override=50.0,
    )
    assert trade.commission == 50.0  # not 42 (auto)
    assert trade.fee_source == "manual_override"
    # total_value = notional + override_commission + 0 + 1.68 = 168000 + 50 + 1.68
    assert trade.total_value == pytest.approx(168051.68, abs=0.01)


def test_historical_fee_config_selected_by_filled_at(db_session, setup):
    """Trade filled before effective_from should pick older config."""
    # 添加一个 2022 年的旧费率
    db_session.add(BrokerFeeConfig(
        broker_name="default",
        commission_rate=0.0003, commission_min=5.0,
        stamp_duty_rate=0.001,  # 旧印花税 0.1%
        transfer_fee_rate=0.00002,
        effective_from=date(2022, 1, 1), is_active=True,
    ))
    db_session.flush()
    # v2: seed a Holding so the SELL has available quantity (no trade->holding sync).
    _seed_settled_buy(db_session, quantity=100, buy_price=1680.0, buy_date=date(2022, 5, 31))
    # 用 2022-06-01 成交日; price out of band for setup prev_close=1680,
    # use force=True to focus this test on fee-config selection.
    trade = record_trade(db_session, stock_code="600519", side="SELL",
                         price=1000.0, quantity=100,
                         filled_at=datetime(2022, 6, 1, 10, 0),
                         source="manual", force=True)
    # 卖出:100000 - max(30, 5) - 100 - 2 = 100000 - 30 - 100 - 2 = 99868
    assert trade.commission == pytest.approx(30.0, abs=0.01)  # 100000 × 0.0003 = 30
    assert trade.stamp_duty == pytest.approx(100.0, abs=0.01)  # 100000 × 0.001 = 100 (旧税率)
    assert trade.transfer_fee == pytest.approx(2.0, abs=0.01)  # 100000 × 0.00002


def test_source_ref_stored(db_session, setup):
    """source_ref (e.g. draft_id) should be stored."""
    trade = record_trade(db_session, stock_code="600519", side="BUY",
                         price=1680.0, quantity=10,
                         filled_at=datetime(2026, 6, 12, 10, 0),
                         source="manual", source_ref="draft:42")
    assert trade.source_ref == "draft:42"


def test_dividend_trade_no_cash_check(db_session, setup):
    """DIVIDEND trades add cash, don't need balance check."""
    trade = record_trade(db_session, stock_code="600519", side="DIVIDEND",
                         price=0.5, quantity=1000,
                         filled_at=datetime(2026, 6, 12, 10, 0),
                         source="corp_action")
    assert trade.quantity == 0
    assert trade.total_value == pytest.approx(-500.0, abs=0.01)  # cash inflow
    cb = db_session.query(CashBalance).first()
    # 200000 + 500
    assert cb.balance == pytest.approx(200500.0, abs=0.01)
