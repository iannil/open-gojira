"""Tests for alert_service — event-driven rules only.

stop_profit retired (decision 2-A 2026-06-26); these exercise the alert
plumbing (create / evaluate / dedupe / ack) via the dividend_ex_date_near rule.
"""

from datetime import date, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models.alert import AlertEvent
from app.models.dividend import DividendRecord
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


def _add_upcoming_dividend(db, code="600519", days_ahead=3):
    db.add(DividendRecord(
        stock_code=code,
        ex_date=date.today() + timedelta(days=days_ahead),
        amount_per_share=2.5,
        quantity_held=0,
        total_received=0.0,
    ))
    db.commit()


def test_create_rule_unknown_type(db: Session):
    with pytest.raises(HTTPException) as e:
        svc.create_rule(db, {"rule_type": "foo", "stock_code": "600941"})
    assert e.value.status_code == 400


def test_create_rule_unknown_stock(db: Session):
    with pytest.raises(HTTPException) as e:
        svc.create_rule(db, {"rule_type": "dividend_ex_date_near", "stock_code": "999999"})
    assert e.value.status_code == 404


def test_create_rule_rejects_removed_type(db: Session):
    with pytest.raises(HTTPException) as e:
        svc.create_rule(db, {"rule_type": "stop_profit", "stock_code": "600941"})
    assert e.value.status_code == 400


def test_dividend_alert_fires_when_ex_date_near(db: Session):
    _add_upcoming_dividend(db, "600519", days_ahead=3)
    svc.create_rule(db, {"rule_type": "dividend_ex_date_near", "stock_code": "600519"})
    result = svc.evaluate_all_rules(db)
    assert result["new_events"] == 1


def test_dividend_alert_skipped_when_no_upcoming(db: Session):
    svc.create_rule(db, {"rule_type": "dividend_ex_date_near", "stock_code": "600519"})
    result = svc.evaluate_all_rules(db)
    assert result["new_events"] == 0


def test_dedupe_within_window(db: Session):
    _add_upcoming_dividend(db, "600519", days_ahead=3)
    svc.create_rule(db, {"rule_type": "dividend_ex_date_near", "stock_code": "600519"})
    svc.evaluate_all_rules(db)
    result2 = svc.evaluate_all_rules(db)
    assert result2["new_events"] == 0
    assert db.query(AlertEvent).count() == 1


def test_ack_event_and_unacked_count(db: Session):
    _add_upcoming_dividend(db, "600519", days_ahead=3)
    svc.create_rule(db, {"rule_type": "dividend_ex_date_near", "stock_code": "600519"})
    svc.evaluate_all_rules(db)
    assert svc.unacked_count(db) == 1
    ev = db.query(AlertEvent).first()
    svc.ack_event(db, ev.id)
    assert svc.unacked_count(db) == 0


def test_no_rules_returns_zero(db: Session):
    result = svc.evaluate_all_rules(db)
    assert result == {"evaluated_rules": 0, "new_events": 0}
