"""Sell-draft generation on thesis invalidation (P0-3).

When a holding's thesis is INVALIDATED, the system auto-generates a SELL draft
(100% by default) carrying a suggested sell price, and supersedes any pending
BUY drafts for that stock (渣男理论: don't add to a broken thesis). The position
gate is trade-derived (Q2-A).
"""
from datetime import datetime

import pytest

from app.models.draft import Draft
from app.models.stock import Stock
from app.models.trade import Trade
from app.services.draft_service import create_thesis_breach_sell_draft


@pytest.fixture
def db_session():
    from tests.conftest import TestSessionLocal
    s = TestSessionLocal()
    try:
        yield s
    finally:
        s.close()


def _seed_position(db, code="600519", qty=100, price=100.0):
    db.add(Stock(code=code, name=code, prev_close=price))
    db.add(Trade(stock_code=code, side="BUY", price=price, quantity=qty,
                 filled_at=datetime(2026, 1, 10, 10, 0), total_value=price * qty,
                 source="manual"))
    db.commit()


def test_thesis_breach_creates_sell_draft_when_held(db_session):
    _seed_position(db_session)
    draft = create_thesis_breach_sell_draft(
        db_session, stock_code="600519", reason="OCF/NI 连续 2 期崩", target_price=95.0,
    )
    db_session.commit()
    assert draft is not None
    assert draft.side == "SELL"
    assert draft.step_kind == "thesis_breach"
    assert draft.reduce_pct_of_position == 1.0
    assert draft.target_price == 95.0
    assert draft.status == "pending"

    # P0-4: an in-app signal alert is raised to prompt manual broker action.
    from app.models.system_alert import SystemAlert
    alert = db_session.query(SystemAlert).filter(SystemAlert.category == "signal").first()
    assert alert is not None
    assert "600519" in alert.message


def test_no_sell_draft_when_not_held(db_session):
    db_session.add(Stock(code="600519", name="x", prev_close=100.0))
    db_session.commit()
    draft = create_thesis_breach_sell_draft(
        db_session, stock_code="600519", reason="x", target_price=95.0,
    )
    assert draft is None


def test_sell_draft_supersedes_pending_buys(db_session):
    _seed_position(db_session)
    db_session.add(Draft(code="600519", side="BUY", status="pending",
                         step_kind="aggressive", step_index=0, reason="加仓"))
    db_session.commit()

    create_thesis_breach_sell_draft(
        db_session, stock_code="600519", reason="论点死", target_price=95.0,
    )
    db_session.commit()

    buy = db_session.query(Draft).filter(Draft.code == "600519", Draft.side == "BUY").one()
    assert buy.status == "superseded"
