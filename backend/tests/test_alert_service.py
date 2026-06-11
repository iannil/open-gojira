"""Tests for alert_service — event-driven rules only."""

from datetime import date, timedelta
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models.alert import AlertEvent
from app.models.holding import Holding
from app.models.stock import Stock
from app.services import alert_service as svc


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    session.add(Stock(code="600941", name="中国移动"))
    session.add(Stock(code="600519", name="贵州茅台"))
    session.commit()
    yield session
    session.close()


def test_create_rule_unknown_type(db: Session):
    with pytest.raises(HTTPException) as e:
        svc.create_rule(db, {"rule_type": "foo", "stock_code": "600941"})
    assert e.value.status_code == 400


def test_create_rule_unknown_stock(db: Session):
    with pytest.raises(HTTPException) as e:
        svc.create_rule(db, {"rule_type": "stop_profit", "stock_code": "999999"})
    assert e.value.status_code == 404


def test_create_rule_rejects_removed_type(db: Session):
    with pytest.raises(HTTPException) as e:
        svc.create_rule(db, {"rule_type": "pe_percentile_cross", "stock_code": "600941"})
    assert e.value.status_code == 400


def test_stop_profit_fires_when_price_exceeds(db: Session):
    db.add(
        Holding(
            stock_code="600519",
            buy_date=date.today() - timedelta(days=30),
            buy_price=1000.0,
            quantity=100,
            stop_profit_price=1500.0,
        )
    )
    db.commit()
    svc.create_rule(db, {"rule_type": "stop_profit", "stock_code": "600519"})
    fake = {"600519": {"sp": 1600.0}}
    with patch.object(svc, "_fetch_realtime", return_value=fake):
        result = svc.evaluate_all_rules(db)
    assert result["new_events"] == 1


def test_stop_profit_skipped_when_no_holding(db: Session):
    svc.create_rule(db, {"rule_type": "stop_profit", "stock_code": "600519"})
    fake = {"600519": {"sp": 9999.0}}
    with patch.object(svc, "_fetch_realtime", return_value=fake):
        result = svc.evaluate_all_rules(db)
    assert result["new_events"] == 0


def test_dedupe_within_window(db: Session):
    svc.create_rule(db, {"rule_type": "stop_profit", "stock_code": "600519"})
    db.add(
        Holding(
            stock_code="600519",
            buy_date=date.today() - timedelta(days=30),
            buy_price=1000.0,
            quantity=100,
            stop_profit_price=1500.0,
        )
    )
    db.commit()
    fake = {"600519": {"sp": 1600.0}}
    with patch.object(svc, "_fetch_realtime", return_value=fake):
        svc.evaluate_all_rules(db)
        result2 = svc.evaluate_all_rules(db)
    assert result2["new_events"] == 0
    assert db.query(AlertEvent).count() == 1


def test_ack_event_and_unacked_count(db: Session):
    db.add(
        Holding(
            stock_code="600519",
            buy_date=date.today() - timedelta(days=30),
            buy_price=1000.0,
            quantity=100,
            stop_profit_price=1500.0,
        )
    )
    db.commit()
    svc.create_rule(db, {"rule_type": "stop_profit", "stock_code": "600519"})
    fake = {"600519": {"sp": 1600.0}}
    with patch.object(svc, "_fetch_realtime", return_value=fake):
        svc.evaluate_all_rules(db)
    assert svc.unacked_count(db) == 1
    ev = db.query(AlertEvent).first()
    svc.ack_event(db, ev.id)
    assert svc.unacked_count(db) == 0


def test_no_rules_returns_zero(db: Session):
    result = svc.evaluate_all_rules(db)
    assert result == {"evaluated_rules": 0, "new_events": 0}
