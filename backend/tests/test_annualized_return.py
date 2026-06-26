"""Annualized return in trade-derived portfolio summary (Q2-A).

Positions come from the Trade ledger; buy_date is the earliest BUY's fill date.
"""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.models.stock import Stock
from app.models.trade import Trade
from app.services.holding_service import get_portfolio_summary
from tests.conftest import TestSessionLocal


@pytest.fixture
def db():
    s = TestSessionLocal()
    try:
        yield s
    finally:
        s.close()


def _buy(db, code, qty, price, days_ago):
    when = datetime.now() - timedelta(days=days_ago)
    db.add(Trade(stock_code=code, side="BUY", price=price, quantity=qty,
                 filled_at=when, total_value=price * qty, source="manual"))


def test_annualized_return_one_year_50pct(db):
    """Buy at 10, current 15, held 365d → annualized ≈ 50%."""
    db.add(Stock(code="X", name="X", industry="A"))
    _buy(db, "X", 100, 10.0, days_ago=365)
    db.commit()
    with patch("app.services.holding_service._get_cached_price", return_value=15.0):
        summary = get_portfolio_summary(db)
    h = summary["holdings"][0]
    assert h["annualized_return_pct"] == pytest.approx(50.0, abs=0.5)


def test_annualized_skipped_when_under_30_days(db):
    db.add(Stock(code="X", name="X", industry="A"))
    _buy(db, "X", 100, 10.0, days_ago=10)
    db.commit()
    with patch("app.services.holding_service._get_cached_price", return_value=15.0):
        summary = get_portfolio_summary(db)
    assert summary["holdings"][0]["annualized_return_pct"] is None


def test_portfolio_annualized_weighted(db):
    db.add(Stock(code="A", name="A", industry="X"))
    db.add(Stock(code="B", name="B", industry="X"))
    _buy(db, "A", 100, 10.0, days_ago=365)
    _buy(db, "B", 100, 10.0, days_ago=365)
    db.commit()
    # A doubles (value 2000, +100%), B halves (value 500, -50%); weighted by value:
    # (2000*100 + 500*(-50)) / 2500 = 70
    with patch("app.services.holding_service._get_cached_price",
               side_effect=lambda code: 20.0 if code == "A" else 5.0):
        summary = get_portfolio_summary(db)
    assert summary["portfolio_annualized_pct"] == pytest.approx(70.0, abs=0.5)
