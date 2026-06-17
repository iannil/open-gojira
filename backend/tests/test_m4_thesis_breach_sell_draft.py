"""M4 (Batch 5 2026-06-17): thesis breach → auto SELL draft (渣男理论).

invest1 第13章 + invest2 §3 "渣男理论: 不谈恋爱,只谈逻辑".
论点证伪 → 系统自动生成 SELL draft (plan_id=NULL, step_kind='thesis_breach')
+ supersede 该 stock 的所有 pending BUY drafts.
"""
from __future__ import annotations

from unittest.mock import patch

from app.core.event_handlers import on_thesis_alert_triggered
from app.core.events import ThesisAlertTriggered
from app.models.draft import Draft
from app.models.plan import Plan
from app.models.stock import Stock
from app.models.trade import Trade
from app.models.cash_balance import CashBalance
from app.models.dividend import DividendRecord  # noqa: F401 (relationship bootstrap)
from app.models.valuation import ValuationSnapshot  # noqa: F401
from app.services.draft_service import (
    create_thesis_breach_sell_draft,
    emit,
    _supersede_pending_buys_for_stock,
)


def _make_event(**overrides) -> ThesisAlertTriggered:
    defaults = dict(
        claim_var_id=42,
        code="601398",
        stock_name="工商银行",
        variable_name="净息差",
        current_value=1.2,
        threshold_value=1.3,
        breach_when="lt",
        window_periods=2,
        message="工商银行(601398) 净息差=1.2%, 连续 2 期 < 1.3%",
    )
    defaults.update(overrides)
    return ThesisAlertTriggered(**defaults)


def _seed_holding(db, code="601398", quantity=1000, avg_cost=5.0):
    """Insert a minimal Stock + Trade so get_holding_view returns one open position."""
    from datetime import datetime
    db.add(Stock(code=code, name=f"测试股 {code}"))
    db.add(CashBalance(balance=100000.0))
    db.flush()
    db.add(Trade(
        stock_code=code,
        side="BUY",
        quantity=quantity,
        price=avg_cost,
        filled_at=datetime(2026, 6, 1, 10, 0, 0),
        commission=5.0,
        stamp_duty=5.0,
        transfer_fee=1.0,
        total_value=quantity * avg_cost + 11.0,
        source="manual",
        fee_source="auto",
    ))
    db.flush()


class TestM4ThesisBreachSellDraft:
    def test_creates_sell_draft_when_stock_held(self, db_session):
        """thesis breach + open holding → SELL draft created with step_kind=thesis_breach."""
        db = db_session
        _seed_holding(db, code="601398")

        draft = create_thesis_breach_sell_draft(
            db,
            stock_code="601398",
            reason="净息差 1.2% 持续 2 期 < 1.3%",
            claim_var_id=42,
        )

        assert draft is not None
        assert draft.code == "601398"
        assert draft.side == "SELL"
        assert draft.step_kind == "thesis_breach"
        assert draft.plan_id is None
        assert draft.reduce_pct_of_position == 1.0
        assert "M4 渣男理论" in draft.reason
        assert "claim_var_id=42" in draft.reason

    def test_no_sell_draft_when_stock_not_held(self, db_session):
        """thesis breach + NO open holding → returns None, no draft."""
        db = db_session
        # No holding seeded
        draft = create_thesis_breach_sell_draft(
            db,
            stock_code="601398",
            reason="净息差 breach",
            claim_var_id=42,
        )
        assert draft is None
        assert db.query(Draft).count() == 0

    def test_supersede_pending_buys(self, db_session):
        """thesis breach + pending BUY drafts → all BUYs marked 'superseded'."""
        db = db_session
        _seed_holding(db, code="601398")

        # Create a fake Plan + pending BUY drafts
        plan = Plan(
            name="test-plan",
            slug="test-plan",
            status="active",
            scan_scope_json='{"type":"custom","values":[]}',
            strategy_composition_json='{"strategy_ids":[]}',
        )
        db.add(plan)
        db.flush()
        for step in (1, 2):
            emit(
                db,
                plan=plan,
                stock_code="601398",
                side="BUY",
                step_kind="buy_ladder",
                step_index=step,
                reason=f"dyr 6% triggered (step {step})",
                add_pct=0.05,
            )

        assert db.query(Draft).filter(Draft.side == "BUY", Draft.status == "pending").count() == 2

        # Fire breach → SELL draft + BUYs superseded
        draft = create_thesis_breach_sell_draft(
            db,
            stock_code="601398",
            reason="OCF/NI breach",
            claim_var_id=42,
        )
        assert draft is not None
        assert "superseded 2" in draft.reason

        # All BUYs now superseded
        pending_buys = db.query(Draft).filter(
            Draft.side == "BUY", Draft.status == "pending"
        ).count()
        superseded_buys = db.query(Draft).filter(
            Draft.side == "BUY", Draft.status == "superseded"
        ).count()
        assert pending_buys == 0
        assert superseded_buys == 2

    def test_idempotent_does_not_duplicate_sell_draft(self, db_session):
        """Multiple breaches for same stock → only one pending SELL draft."""
        db = db_session
        _seed_holding(db, code="601398")

        d1 = create_thesis_breach_sell_draft(
            db, stock_code="601398", reason="first breach", claim_var_id=1,
        )
        d2 = create_thesis_breach_sell_draft(
            db, stock_code="601398", reason="second breach", claim_var_id=2,
        )

        assert d1.id == d2.id  # same draft updated in place
        assert db.query(Draft).filter(
            Draft.side == "SELL", Draft.status == "pending",
            Draft.step_kind == "thesis_breach",
        ).count() == 1


class TestM4HandlerIntegration:
    """on_thesis_alert_triggered end-to-end test."""

    def test_handler_creates_sell_draft_for_held_stock(self, db_session):
        db = db_session
        _seed_holding(db, code="601398")

        with patch("app.db.session.SessionLocal") as mock_sl, \
             patch("app.services.notification_service.dispatch_alert"):
            mock_sl.return_value.__enter__.return_value = db
            mock_sl.return_value.__exit__.return_value = None
            on_thesis_alert_triggered(_make_event())

        drafts = db.query(Draft).filter(
            Draft.side == "SELL",
            Draft.step_kind == "thesis_breach",
            Draft.status == "pending",
        ).all()
        assert len(drafts) == 1
        assert drafts[0].code == "601398"
        assert drafts[0].plan_id is None

    def test_handler_skips_when_not_held(self, db_session):
        db = db_session
        # No holding seeded

        with patch("app.db.session.SessionLocal") as mock_sl, \
             patch("app.services.notification_service.dispatch_alert"):
            mock_sl.return_value.__enter__.return_value = db
            mock_sl.return_value.__exit__.return_value = None
            on_thesis_alert_triggered(_make_event())

        # audit_log written, but no SELL draft
        assert db.query(Draft).count() == 0
