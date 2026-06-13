"""Test position_advisor using holding_view_service.

S1.11 invariant: position_advisor reads derived holdings (from trades via
holding_view_service.get_holding_view), not the legacy Holding table.

These tests seed state via record_trade (the canonical write path) and
verify that portfolio constraints behave correctly end-to-end.
"""
from datetime import datetime, date

import pytest

from app.models.broker_fee_config import BrokerFeeConfig
from app.models.cash_balance import CashBalance
from app.models.stock import Stock
from app.services.position_advisor_service import check_before_draft
from app.services.trade_service import record_trade


@pytest.fixture
def setup(db_session):
    """Seed stocks + cash + broker fee config so record_trade can write."""
    db_session.add(Stock(
        code="600519", name="贵州茅台", exchange="sh", industry="白酒",
        listing_status="normally_listed", prev_close=100.0,
    ))
    db_session.add(Stock(
        code="000001", name="平安银行", exchange="sz", industry="银行",
        listing_status="normally_listed", prev_close=15.0,
    ))
    db_session.add(Stock(
        code="600036", name="招商银行", exchange="sh", industry="银行",
        listing_status="normally_listed", prev_close=50.0,
    ))
    db_session.add(CashBalance(id=1, balance=1_000_000.0))
    db_session.add(
        BrokerFeeConfig(
            broker_name="default",
            commission_rate=0.00025,
            commission_min=5.0,
            stamp_duty_rate=0.0005,
            transfer_fee_rate=0.00001,
            effective_from=date(2023, 10, 23),
            is_active=True,
        )
    )
    db_session.flush()


def test_check_no_holdings_can_open(db_session, setup):
    """Empty portfolio: BUY should be allowed, count is 0."""
    advice = check_before_draft(db_session, stock_code="600519", side="BUY")
    assert advice.can_open_new is True
    assert advice.holdings_count == 0


def test_check_industry_concentration(db_session, setup):
    """If industry weight is at limit, BUY of NEW bank stock is blocked."""
    # Buy two bank stocks — bank industry now ~100% of portfolio.
    record_trade(
        db_session,
        stock_code="000001",
        side="BUY",
        price=15.0,
        quantity=1000,
        filled_at=datetime(2026, 6, 1, 10, 0),
        source="manual",
    )
    record_trade(
        db_session,
        stock_code="600036",
        side="BUY",
        price=50.0,
        quantity=300,
        filled_at=datetime(2026, 6, 1, 10, 0),
        source="manual",
    )

    # Adding to existing bank stock bypasses industry check — so add a NEW bank.
    db_session.add(Stock(code="600000", name="浦发银行", exchange="sh", industry="银行"))
    db_session.flush()

    advice = check_before_draft(db_session, stock_code="600000", side="BUY")
    assert any("银行" in b for b in advice.blockers)


def test_check_holdings_count_limit(db_session, setup):
    """Max 4 open holdings; BUY of 5th (different industry) should be blocked."""
    # Seed 4 distinct-industry holdings so industry check doesn't fire first.
    # Note: 600519/000001/600036 are already seeded by the `setup` fixture.
    new_stocks = [
        ("300750", "宁德时代", "sz", "电池", 200.0),
        ("600276", "恒瑞医药", "sh", "医药", 50.0),
    ]
    for code, name, exch, ind, pc in new_stocks:
        db_session.add(Stock(
            code=code, name=name, exchange=exch, industry=ind,
            listing_status="normally_listed", prev_close=pc,
        ))
    db_session.flush()

    record_trade(
        db_session,
        stock_code="600519",
        side="BUY",
        price=100,
        quantity=10,
        filled_at=datetime(2026, 6, 1, 10, 0),
        source="manual",
    )
    record_trade(
        db_session,
        stock_code="000001",
        side="BUY",
        price=15,
        quantity=100,
        filled_at=datetime(2026, 6, 1, 10, 0),
        source="manual",
    )
    record_trade(
        db_session,
        stock_code="300750",
        side="BUY",
        price=200,
        quantity=5,
        filled_at=datetime(2026, 6, 1, 10, 0),
        source="manual",
    )
    record_trade(
        db_session,
        stock_code="600276",
        side="BUY",
        price=50,
        quantity=20,
        filled_at=datetime(2026, 6, 1, 10, 0),
        source="manual",
    )

    # Try opening a 5th distinct-industry position.
    db_session.add(Stock(code="601318", name="中国平安", exchange="sh", industry="保险"))
    db_session.flush()
    advice = check_before_draft(db_session, stock_code="601318", side="BUY")

    # 4 holdings + 0 pending → effective_count=4 → at max → blocker.
    assert advice.holdings_count == 4
    assert not advice.can_open_new
    assert any("超过上限" in b for b in advice.blockers)


def test_sell_always_allowed(db_session, setup):
    """SELL is always allowed regardless of state."""
    advice = check_before_draft(db_session, stock_code="600519", side="SELL")
    assert advice.can_open_new is True


def test_add_to_existing_position_no_industry_block(db_session, setup):
    """Adding to an existing position bypasses industry concentration check."""
    record_trade(
        db_session,
        stock_code="000001",
        side="BUY",
        price=15.0,
        quantity=1000,
        filled_at=datetime(2026, 6, 1, 10, 0),
        source="manual",
    )
    # Bank industry is now 100% — but adding to same stock must NOT be blocked.
    advice = check_before_draft(db_session, stock_code="000001", side="BUY")
    assert not any("银行" in b for b in advice.blockers)
