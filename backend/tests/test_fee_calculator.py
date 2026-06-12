"""Test fee_calculator_service — commission / stamp_duty / transfer_fee."""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.broker_fee_config import BrokerFeeConfig
from app.services.fee_calculator_service import FeeBreakdown, compute_fees


# ---------------------------------------------------------------------------
# Fixtures — local in-memory SQLite (matches test_broker_fee_config convention)
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
def cfg(db_session):
    """Standard 2023-10-23+ rates."""
    c = BrokerFeeConfig(
        broker_name="default",
        commission_rate=0.00025,
        commission_min=5.0,
        stamp_duty_rate=0.0005,
        transfer_fee_rate=0.00001,
        effective_from=date(2023, 10, 23),
        is_active=True,
    )
    db_session.add(c)
    db_session.flush()
    return c


def test_buy_fees(cfg):
    # 1680 × 100 = 168000
    # 佣金 = max(168000 × 0.00025, 5) = 42
    # 印花税 = 0(买方不收)
    # 过户费 = 168000 × 0.00001 = 1.68
    fees = compute_fees(side="BUY", price=1680.0, quantity=100, broker_config=cfg)
    assert fees.commission == 42.0
    assert fees.stamp_duty == 0.0
    assert fees.transfer_fee == pytest.approx(1.68, abs=0.01)


def test_sell_fees(cfg):
    # 卖出:佣金 + 印花税 + 过户费
    fees = compute_fees(side="SELL", price=1680.0, quantity=100, broker_config=cfg)
    assert fees.commission == 42.0
    assert fees.stamp_duty == pytest.approx(84.0, abs=0.01)  # 168000 × 0.0005
    assert fees.transfer_fee == pytest.approx(1.68, abs=0.01)


def test_min_commission_kicks_in(cfg):
    # 1680 × 1 = 1680 元,佣金 = max(0.42, 5) = 5
    fees = compute_fees(side="BUY", price=1680.0, quantity=1, broker_config=cfg)
    assert fees.commission == 5.0


def test_min_commission_boundary(cfg):
    # 临界:notional × rate 刚好 = min
    # commission_rate=0.00025, commission_min=5.0
    # notional × 0.00025 = 5.0 → notional = 20000
    # 100 股 × 200 元 = 20000
    fees = compute_fees(side="BUY", price=200.0, quantity=100, broker_config=cfg)
    assert fees.commission == 5.0  # 临界点取 max(5, 5) = 5

    # 略低于临界
    fees_below = compute_fees(side="BUY", price=199.99, quantity=100, broker_config=cfg)
    assert fees_below.commission == 5.0  # 4.99975 < 5, 取 5

    # 略高于临界
    fees_above = compute_fees(side="BUY", price=200.01, quantity=100, broker_config=cfg)
    assert fees_above.commission == pytest.approx(5.00025, abs=0.001)


def test_total_value_buy_includes_fees(cfg):
    # BUY total_value = notional + commission + stamp_duty + transfer_fee
    # = 168000 + 42 + 0 + 1.68 = 168043.68
    fees = compute_fees(side="BUY", price=1680.0, quantity=100, broker_config=cfg)
    assert fees.total_value("BUY") == pytest.approx(168043.68, abs=0.01)


def test_total_value_sell_excludes_fees(cfg):
    # SELL total_value = notional - commission - stamp_duty - transfer_fee
    # = 168000 - 42 - 84 - 1.68 = 167872.32
    fees = compute_fees(side="SELL", price=1680.0, quantity=100, broker_config=cfg)
    assert fees.total_value("SELL") == pytest.approx(167872.32, abs=0.01)


def test_total_value_dividend_negative(cfg):
    # DIVIDEND: total_value = -notional (cash inflow)
    fees = compute_fees(side="DIVIDEND", price=0.5, quantity=1000, broker_config=cfg)
    # notional = 500
    assert fees.total_value("DIVIDEND") == pytest.approx(-500.0, abs=0.01)


def test_total_value_corp_action_zero(cfg):
    # CORP_ACTION: 送股,price=0,no cash impact
    fees = compute_fees(side="CORP_ACTION", price=0.0, quantity=100, broker_config=cfg)
    assert fees.total_value("CORP_ACTION") == 0.0


def test_fees_with_zero_min_commission(db_session):
    """If min is 0, commission = notional × rate (no floor)."""
    cfg = BrokerFeeConfig(
        broker_name="zero_min",
        commission_rate=0.001,
        commission_min=0.0,
        stamp_duty_rate=0.0005,
        transfer_fee_rate=0.0,
        effective_from=date(2024, 1, 1),
        is_active=True,
    )
    fees = compute_fees(side="BUY", price=10.0, quantity=1, broker_config=cfg)
    # notional = 10, commission = max(10 × 0.001, 0) = 0.01
    assert fees.commission == pytest.approx(0.01, abs=0.001)
    assert fees.transfer_fee == 0.0
