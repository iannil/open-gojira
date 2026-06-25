"""Test trade_service hard constraints — T+1 + price band."""
from datetime import datetime, date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.cash_balance import CashBalance
from app.models.broker_fee_config import BrokerFeeConfig
from app.models.holding import Holding
from app.models.stock import Stock


def _add_holding(db, code="600519", quantity=100, buy_price=100.0):
    """v2: sellable quantity comes from Holding (CSV import), not from BUY
    trades (no trade->holding sync). Tests exercising a successful SELL seed a
    Holding first."""
    db.add(Holding(
        stock_code=code, buy_date=date(2026, 6, 11), buy_price=buy_price,
        quantity=quantity, stop_profit_price=buy_price * 1.3,
    ))
    db.flush()
from app.services.trade_service import (
    record_trade,
    InsufficientQuantityError,
)
from app.services.price_validator_service import (
    PriceOutOfBandError,
    StockSuspendedError,
)


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
    db_session.add(Stock(
        code="600519", name="贵州茅台", exchange="sh",
        listing_status="normally_listed", prev_close=100.0,
    ))
    db_session.add(Stock(
        code="300750", name="宁德时代", exchange="sz",
        listing_status="normally_listed", prev_close=200.0,
    ))
    db_session.add(Stock(
        code="600001", name="*ST 邯郸", exchange="sh",
        listing_status="delisting_risk_warning", prev_close=10.0,
    ))
    db_session.add(CashBalance(id=1, balance=1000000.0))
    db_session.add(BrokerFeeConfig(
        broker_name="default", commission_rate=0.00025, commission_min=5.0,
        stamp_duty_rate=0.0005, transfer_fee_rate=0.00001,
        effective_from=date(2023, 10, 23), is_active=True,
    ))
    db_session.flush()


# --- available quantity 校验 (v2: 基于 Holding, 无 trade-T+1) -----------------
# v1 的 trade-based T+1 (今日买入今日冻结) 已弃用: v2 持仓来自 CSV, available
# 读 Holding.quantity, 无日期冻结逻辑 (trading-philosophy 决策 2026-06-25).

def test_sell_full_holding_ok(db_session, setup):
    """v2: 持有 100 (Holding) 可全部卖出."""
    _add_holding(db_session, quantity=100)
    trade = record_trade(db_session, stock_code="600519", side="SELL",
                         price=101.0, quantity=100,
                         filled_at=datetime(2026, 6, 12, 14, 0), source="manual")
    assert trade.quantity == -100


def test_sell_partial_of_holding_ok(db_session, setup):
    """v2: 持有 200 (Holding) 部分卖出 100 (够)."""
    _add_holding(db_session, quantity=200)
    trade = record_trade(db_session, stock_code="600519", side="SELL",
                         price=101.0, quantity=100,
                         filled_at=datetime(2026, 6, 12, 14, 0), source="manual")
    assert trade.quantity == -100


def test_sell_exceeding_available_raises(db_session, setup):
    """试图卖超过持仓 (Holding 100, 卖 200)."""
    _add_holding(db_session, quantity=100)
    with pytest.raises(InsufficientQuantityError):
        record_trade(db_session, stock_code="600519", side="SELL",
                     price=101.0, quantity=200,
                     filled_at=datetime(2026, 6, 12, 14, 0), source="manual")


def test_sell_with_zero_position_raises(db_session, setup):
    """没持仓试图卖."""
    with pytest.raises(InsufficientQuantityError):
        record_trade(db_session, stock_code="600519", side="SELL",
                     price=101.0, quantity=100,
                     filled_at=datetime(2026, 6, 12, 14, 0), source="manual")


# --- 价格校验 ----------------------------------------------------------------

def test_buy_above_upper_limit_raises(db_session, setup):
    """主板 prev_close=100, upper=110, price=115 超出."""
    with pytest.raises(PriceOutOfBandError):
        record_trade(db_session, stock_code="600519", side="BUY",
                     price=115.0, quantity=10,
                     filled_at=datetime(2026, 6, 12, 10, 0), source="manual")


def test_buy_at_upper_limit_ok(db_session, setup):
    """prev_close=100, price=110 边界 OK."""
    trade = record_trade(db_session, stock_code="600519", side="BUY",
                         price=110.0, quantity=10,
                         filled_at=datetime(2026, 6, 12, 10, 0), source="manual")
    assert trade.id is not None


def test_buy_below_lower_limit_raises(db_session, setup):
    with pytest.raises(PriceOutOfBandError):
        record_trade(db_session, stock_code="600519", side="BUY",
                     price=85.0, quantity=10,
                     filled_at=datetime(2026, 6, 12, 10, 0), source="manual")


def test_buy_st_stock_uses_5pct_band(db_session, setup):
    """*ST prev_close=10, band=±5% → [9.5, 10.5]."""
    with pytest.raises(PriceOutOfBandError):
        record_trade(db_session, stock_code="600001", side="BUY",
                     price=11.5, quantity=100,  # 15% above, exceeds ±5%
                     filled_at=datetime(2026, 6, 12, 10, 0), source="manual")


def test_buy_chinext_uses_20pct_band(db_session, setup):
    """chinext prev_close=200, band=±20% → [160, 240]."""
    trade = record_trade(db_session, stock_code="300750", side="BUY",
                         price=230.0, quantity=10,  # 15% above, within ±20%
                         filled_at=datetime(2026, 6, 12, 10, 0), source="manual")
    assert trade.id is not None


def test_buy_suspended_stock_raises(db_session, setup):
    """delisting_risk_warning 不算停牌(只是 ST);ipo_suspension 算停牌."""
    db_session.add(Stock(
        code="600002", name="暂停上市", exchange="sh",
        listing_status="ipo_suspension", prev_close=50.0,
    ))
    db_session.flush()
    with pytest.raises(StockSuspendedError):
        record_trade(db_session, stock_code="600002", side="BUY",
                     price=50.0, quantity=100,
                     filled_at=datetime(2026, 6, 12, 10, 0), source="manual")


# --- force bypass -----------------------------------------------------------

def test_force_bypass_price_check(db_session, setup):
    """force=True 跳过价格校验(用于特殊场景:新股首日 / 复牌)."""
    trade = record_trade(
        db_session, stock_code="600519", side="BUY",
        price=200.0, quantity=10,  # 远超 ±10% 上限
        filled_at=datetime(2026, 6, 12, 10, 0), source="manual",
        force=True,
    )
    assert trade.id is not None
    assert trade.note is not None and "force" in trade.note.lower()


def test_force_does_not_bypass_quantity_check(db_session, setup):
    """force 只旁路价格校验, 不旁路 available-quantity 校验."""
    with pytest.raises(InsufficientQuantityError):
        record_trade(
            db_session, stock_code="600519", side="SELL",
            price=101.0, quantity=100,
            filled_at=datetime(2026, 6, 12, 14, 0), source="manual",
            force=True,  # quantity check still enforced (no holding)
        )


def test_force_does_not_bypass_cash_check(db_session, setup):
    """force 不旁路 cash 不足校验."""
    db_session.add(Stock(
        code="600999", name="招商证券", exchange="sh",
        listing_status="normally_listed", prev_close=10.0,
    ))
    db_session.flush()
    with pytest.raises(Exception) as exc:
        record_trade(
            db_session, stock_code="600999", side="BUY",
            price=10.0, quantity=1000000,  # 需要 1000 万,只有 100 万
            filled_at=datetime(2026, 6, 12, 10, 0), source="manual",
            force=True,
        )
    # InsufficientBalanceError (HTTPException 400)
    assert "Insufficient" in str(exc.value) or exc.value.status_code == 400


# --- DIVIDEND / CORP_ACTION 跳过校验 ----------------------------------------

def test_dividend_skips_price_and_quantity_check(db_session, setup):
    """DIVIDEND 无 price/quantity 概念,跳过校验."""
    trade = record_trade(db_session, stock_code="600519", side="DIVIDEND",
                         price=0.5, quantity=1000,
                         filled_at=datetime(2026, 6, 12, 10, 0),
                         source="corp_action")
    assert trade.id is not None
