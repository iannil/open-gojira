"""Tests for watchlist_service."""

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models.stock import Stock
from app.services import watchlist_service as svc


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    session.add(Stock(code="600519", name="贵州茅台"))
    session.add(Stock(code="000858", name="五粮液"))
    session.commit()
    yield session
    session.close()


def test_default_group_created_on_demand(db: Session):
    g = svc.get_or_create_default_group(db)
    assert g.id is not None
    # Idempotent
    g2 = svc.get_or_create_default_group(db)
    assert g.id == g2.id


def test_create_group_and_add_item(db: Session):
    g = svc.create_group(db, {"name": "白酒"})
    item = svc.add_item(db, g.id, {"stock_code": "600519", "note": "茅台龙头"})
    assert item.id is not None
    assert item.stock_code == "600519"
    # Adding the same stock again returns existing item, not duplicate
    item2 = svc.add_item(db, g.id, {"stock_code": "600519"})
    assert item2.id == item.id


def test_create_group_duplicate_name_rejected(db: Session):
    svc.create_group(db, {"name": "白酒"})
    with pytest.raises(HTTPException) as e:
        svc.create_group(db, {"name": "白酒"})
    assert e.value.status_code == 409


def test_add_item_unknown_stock(db: Session):
    g = svc.create_group(db, {"name": "测试"})
    with pytest.raises(HTTPException) as e:
        svc.add_item(db, g.id, {"stock_code": "999999"})
    assert e.value.status_code == 404


def test_bulk_add_filters_invalid(db: Session):
    g = svc.create_group(db, {"name": "白酒"})
    added = svc.bulk_add_items(db, g.id, ["600519", "000858", "999999"])
    assert added == 2


def test_all_watched_codes_distinct(db: Session):
    g1 = svc.create_group(db, {"name": "组1"})
    g2 = svc.create_group(db, {"name": "组2"})
    svc.add_item(db, g1.id, {"stock_code": "600519"})
    svc.add_item(db, g2.id, {"stock_code": "600519"})
    svc.add_item(db, g2.id, {"stock_code": "000858"})
    assert set(svc.all_watched_codes(db)) == {"600519", "000858"}


def test_update_item(db: Session):
    g = svc.create_group(db, {"name": "测试"})
    item = svc.add_item(db, g.id, {"stock_code": "600519"})
    updated = svc.update_item(db, item.id, {"note": "观察银行股"})
    assert updated.note == "观察银行股"


def test_delete_group_cascades_items(db: Session):
    g = svc.create_group(db, {"name": "测试"})
    svc.add_item(db, g.id, {"stock_code": "600519"})
    assert svc.delete_group(db, g.id) is True
    assert svc.all_watched_codes(db) == []
