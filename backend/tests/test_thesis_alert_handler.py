"""Tests for on_thesis_alert_triggered handler (Phase 2 #9 阶段 B v2).

Verifies the Bug 1 fix: SystemAlert must be created with the model's actual
fields (severity / category / message / detail_json) — no `title` / `source` /
`payload` / `triggered_at`. AttributeError here used to be swallowed by the
broad except block, silently breaking notification dispatch.
"""
from __future__ import annotations

from unittest.mock import patch

from app.core.event_handlers import on_thesis_alert_triggered
from app.core.events import ThesisAlertTriggered
from app.models.system_alert import SystemAlert


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


class TestThesisAlertHandler:
    def test_writes_audit_log(self, db_session):
        """on_thesis_alert_triggered must write audit_log even if notification fails."""
        from app.models.audit_log import AuditLog
        db = db_session
        with patch("app.db.session.SessionLocal") as mock_sl, \
             patch("app.services.notification_service.dispatch_alert"):
            mock_sl.return_value.__enter__.return_value = db
            mock_sl.return_value.__exit__.return_value = None
            on_thesis_alert_triggered(_make_event())

        rows = db.query(AuditLog).filter(
            AuditLog.event == "thesis_alert_triggered",
            AuditLog.entity_id == "42",
        ).all()
        assert len(rows) == 1
        assert "净息差" in rows[0].summary

    def test_writes_system_alert_with_correct_schema(self, db_session):
        """Bug 1 regression: SystemAlert must accept our 4-field schema.

        Before fix: handler tried to set title/source/payload/triggered_at,
        AttributeError was silently caught by broad except, so SystemAlert
        table never got a thesis row.
        """
        db = db_session
        with patch("app.db.session.SessionLocal") as mock_sl, \
             patch("app.services.notification_service.dispatch_alert"):
            mock_sl.return_value.__enter__.return_value = db
            mock_sl.return_value.__exit__.return_value = None
            on_thesis_alert_triggered(_make_event())

        rows = db.query(SystemAlert).filter(SystemAlert.category == "thesis").all()
        assert len(rows) == 1
        sa = rows[0]
        assert sa.severity == "alert"
        assert sa.category == "thesis"
        assert "净息差" in sa.message
        assert "601398" in sa.message
        assert sa.detail_json is not None
        assert sa.detail_json["claim_var_id"] == 42
        assert sa.detail_json["stock_code"] == "601398"
        assert sa.detail_json["source"] == "thesis_monitor"

    def test_dispatch_alert_invoked(self, db_session):
        """dispatch_alert must be called with the new SystemAlert."""
        db = db_session
        with patch("app.db.session.SessionLocal") as mock_sl, \
             patch("app.services.notification_service.dispatch_alert") as mock_dispatch:
            mock_sl.return_value.__enter__.return_value = db
            mock_sl.return_value.__exit__.return_value = None
            on_thesis_alert_triggered(_make_event())

        mock_dispatch.assert_called_once()
        dispatched_alert = mock_dispatch.call_args[0][1]
        assert dispatched_alert.category == "thesis"
        assert dispatched_alert.severity == "alert"
