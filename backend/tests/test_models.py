"""Tests for the core ORM models that survive into the autopilot era."""

from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models import Stock, ValuationSnapshot


def _make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_create_stock():
    session = _make_session()
    stock = Stock(
        code="600519",
        name="Kweichow Moutai",
        industry="Beverage",
        qiu_score=3,
        quadrant="procyclical",
    )
    session.add(stock)
    session.commit()

    result = session.query(Stock).filter_by(code="600519").one()
    assert result.name == "Kweichow Moutai"
    assert result.industry == "Beverage"
    assert result.qiu_score == 3
    assert result.quadrant == "procyclical"
    assert result.created_at is not None


def test_create_valuation_snapshot():
    session = _make_session()
    stock = Stock(code="600519", name="Kweichow Moutai")
    session.add(stock)
    session.flush()

    snapshot = ValuationSnapshot(
        stock_code="600519",
        date=date(2025, 1, 15),
        pe_ttm=35.2,
        pb=12.5,
        pe_percentile_10y=65.0,
        dividend_yield=1.8,
    )
    session.add(snapshot)
    session.commit()

    result = session.query(ValuationSnapshot).one()
    assert result.stock_code == "600519"
    assert result.pe_ttm == 35.2
    assert result.pb == 12.5
    assert result.date == date(2025, 1, 15)
    assert result.created_at is not None


def test_relationships():
    session = _make_session()
    stock = Stock(code="600519", name="Kweichow Moutai")
    session.add(stock)
    session.flush()

    snapshot = ValuationSnapshot(
        stock_code="600519", date=date(2025, 3, 1), pe_ttm=33.0
    )
    session.add(snapshot)
    session.commit()

    loaded = session.query(Stock).filter_by(code="600519").one()
    assert len(loaded.valuations) == 1
    assert loaded.valuations[0].pe_ttm == 33.0
