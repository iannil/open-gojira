"""Tests for security_theme labeling + theme breakdown."""

from datetime import date

import pytest

from app.models.holding import Holding
from app.models.stock import Stock
from app.services.holding_service import get_theme_breakdown
from tests.conftest import TestSessionLocal


@pytest.fixture
def db():
    s = TestSessionLocal()
    try:
        yield s
    finally:
        s.close()


def _seed(db, code: str, theme: str | None, value: int):
    db.add(Stock(code=code, name=code, industry="X", security_theme=theme))
    db.add(Holding(
        stock_code=code, buy_date=date(2025, 1, 1),
        buy_price=10.0, quantity=value // 10, stop_profit_price=0,
    ))


def test_theme_breakdown_aggregates_correctly(db):
    _seed(db, "A", "能源", 60000)
    _seed(db, "B", "金融", 30000)
    _seed(db, "C", "金融", 10000)
    db.commit()
    buckets = get_theme_breakdown(db)
    themes = {b["theme"]: b for b in buckets}
    assert themes["能源"]["weight_pct"] == 60.0
    assert themes["金融"]["weight_pct"] == 40.0
    assert themes["金融"]["count"] == 2


def test_theme_breakdown_treats_null_as_unlabeled(db):
    _seed(db, "A", "能源", 50000)
    _seed(db, "B", None, 50000)
    db.commit()
    buckets = get_theme_breakdown(db)
    themes = {b["theme"] for b in buckets}
    assert "未标注" in themes


def test_theme_breakdown_empty_when_no_holdings(db):
    assert get_theme_breakdown(db) == []
