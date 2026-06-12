"""Test broker_fee_configs model + seeder."""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.broker_fee_config import BrokerFeeConfig
from app.services.builtin_seeder import seed_default_fee_config


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


def test_fee_config_create(db_session):
    cfg = BrokerFeeConfig(
        broker_name="default",
        commission_rate=0.00025,
        commission_min=5.0,
        stamp_duty_rate=0.0005,
        transfer_fee_rate=0.00001,
        effective_from=date(2023, 10, 23),
        is_active=True,
    )
    db_session.add(cfg)
    db_session.commit()
    assert cfg.id is not None
    assert cfg.commission_rate == 0.00025
    assert cfg.is_active is True


def test_fee_config_effective_from_indexed(db_session):
    """effective_from should be indexed (lookup by trade date)."""
    table = BrokerFeeConfig.__table__
    assert table.c.effective_from.index


def test_seeder_inserts_default_if_absent(db_session):
    """seed_default_fee_config should insert one row on empty table."""
    assert db_session.query(BrokerFeeConfig).count() == 0
    seed_default_fee_config(db_session)
    db_session.commit()
    assert db_session.query(BrokerFeeConfig).count() == 1
    cfg = db_session.query(BrokerFeeConfig).first()
    assert cfg.broker_name == "default"
    assert cfg.commission_rate == 0.00025
    assert cfg.commission_min == 5.0
    assert cfg.stamp_duty_rate == 0.0005
    assert cfg.transfer_fee_rate == 0.00001
    assert cfg.effective_from == date(2023, 10, 23)
    assert cfg.is_active is True


def test_seeder_idempotent(db_session):
    """Running seeder twice should not duplicate."""
    seed_default_fee_config(db_session)
    db_session.commit()
    seed_default_fee_config(db_session)
    db_session.commit()
    assert db_session.query(BrokerFeeConfig).count() == 1


def test_fee_config_supports_historical_rates(db_session):
    """Multiple configs with different effective_from for rate changes."""
    db_session.add(BrokerFeeConfig(
        broker_name="default",
        commission_rate=0.0003, commission_min=5.0,
        stamp_duty_rate=0.001,  # pre-2023-08-28 rate
        transfer_fee_rate=0.00002,
        effective_from=date(2022, 1, 1),
        is_active=False,  # historical
    ))
    db_session.add(BrokerFeeConfig(
        broker_name="default",
        commission_rate=0.00025, commission_min=5.0,
        stamp_duty_rate=0.0005,
        transfer_fee_rate=0.00001,
        effective_from=date(2023, 10, 23),
        is_active=True,
    ))
    db_session.commit()
    assert db_session.query(BrokerFeeConfig).count() == 2
