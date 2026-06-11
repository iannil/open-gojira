"""Tests for annualized return computation in holdings & portfolio summary."""

from datetime import date, timedelta
from unittest.mock import patch

import pytest

from app.models.holding import Holding
from app.models.stock import Stock
from app.services.holding_service import _holding_to_dict, get_portfolio_summary
from tests.conftest import TestSessionLocal


@pytest.fixture
def db():
    s = TestSessionLocal()
    try:
        yield s
    finally:
        s.close()


def test_annualized_return_one_year_50pct(db):
    """Buy at 10, current 15, held 365d → annualized ≈ 50%."""
    db.add(Stock(code="X", name="X", industry="A"))
    db.add(Holding(
        stock_code="X", buy_date=date.today() - timedelta(days=365),
        buy_price=10.0, quantity=100, stop_profit_price=0,
    ))
    db.commit()
    h = db.query(Holding).first()
    with patch("app.services.holding_service._get_cached_price", return_value=15.0):
        d = _holding_to_dict(h, db)
    assert d["annualized_return_pct"] == pytest.approx(50.0, abs=0.5)


def test_annualized_skipped_when_under_30_days(db):
    db.add(Stock(code="X", name="X", industry="A"))
    db.add(Holding(
        stock_code="X", buy_date=date.today() - timedelta(days=10),
        buy_price=10.0, quantity=100, stop_profit_price=0,
    ))
    db.commit()
    h = db.query(Holding).first()
    with patch("app.services.holding_service._get_cached_price", return_value=15.0):
        d = _holding_to_dict(h, db)
    assert d["annualized_return_pct"] is None


def test_portfolio_annualized_weighted(db):
    db.add(Stock(code="A", name="A", industry="X"))
    db.add(Stock(code="B", name="B", industry="X"))
    db.add(Holding(
        stock_code="A", buy_date=date.today() - timedelta(days=365),
        buy_price=10.0, quantity=100, stop_profit_price=0,
    ))
    db.add(Holding(
        stock_code="B", buy_date=date.today() - timedelta(days=365),
        buy_price=10.0, quantity=100, stop_profit_price=0,
    ))
    db.commit()
    # A doubles, B halves; equal weights → portfolio ~ avg of +100% and -50%
    with patch("app.services.holding_service._get_cached_price",
               side_effect=lambda code: 20.0 if code == "A" else 5.0):
        summary = get_portfolio_summary(db)
    # Weighting is by current value (2000 vs 500), so A dominates.
    # Per-holding: A=+100%, B=-50%; weighted = (2000*100 + 500*(-50))/2500 = 70
    assert summary["portfolio_annualized_pct"] == pytest.approx(70.0, abs=0.5)
