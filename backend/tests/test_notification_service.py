"""Test notification dispatch + channels."""
from unittest.mock import patch, MagicMock
from datetime import datetime
import pytest

from app.models.notification_channel import NotificationChannel
from app.services.notification_service import (
    dispatch_alert, send_to_channel, _send_server_chan,
    _send_email, _send_dingtalk_webhook, _send_in_app,
    list_channels, create_channel, update_channel, delete_channel,
)
from app.services.system_alert_service import create_alert


@pytest.fixture
def setup_channels(db_session):
    db_session.add(NotificationChannel(
        name="server_chan_main", type="server_chan",
        config_json={"sendkey": "SCT123ABC"},
        enabled=True, severity_filter="warning_and_above",
    ))
    db_session.add(NotificationChannel(
        name="email_backup", type="email",
        config_json={"to": "user@example.com"},
        enabled=True, severity_filter="critical_only",
    ))
    db_session.add(NotificationChannel(
        name="in_app_default", type="in_app",
        config_json={}, enabled=True, severity_filter="all",
    ))
    db_session.flush()


def test_create_channel(db_session):
    ch = create_channel(db_session, name="test", type="email",
                        config={"to": "test@test.com"})
    db_session.commit()
    assert ch.id is not None
    assert ch.enabled is True


def test_list_channels(db_session, setup_channels):
    channels = list_channels(db_session, enabled_only=True)
    assert len(channels) == 3


def test_update_channel(db_session, setup_channels):
    ch = list_channels(db_session)[0]
    updated = update_channel(db_session, ch.id, {"enabled": False})
    db_session.commit()
    assert updated.enabled is False


def test_delete_channel(db_session, setup_channels):
    ch = list_channels(db_session)[0]
    delete_channel(db_session, ch.id)
    db_session.commit()
    assert len(list_channels(db_session)) == 2


def test_dispatch_critical_sends_to_all_channels(db_session, setup_channels):
    """Critical should send to all enabled channels (warning_and_above + critical_only + all)."""
    alert = create_alert(db_session, severity="critical", category="data",
                          message="Test critical", detail={"x": 1})
    db_session.flush()

    with patch("app.services.notification_service._send_server_chan") as sc, \
         patch("app.services.notification_service._send_email") as em, \
         patch("app.services.notification_service._send_in_app") as ia:
        sc.return_value = True
        em.return_value = True
        ia.return_value = True
        results = dispatch_alert(db_session, alert)
    assert len(results) == 3
    assert all(r.success for r in results)


def test_dispatch_warning_skips_critical_only(db_session, setup_channels):
    """Warning should NOT go to critical_only filter."""
    alert = create_alert(db_session, severity="warning", category="api",
                          message="Test warning")
    db_session.flush()
    with patch("app.services.notification_service._send_server_chan") as sc, \
         patch("app.services.notification_service._send_email") as em, \
         patch("app.services.notification_service._send_in_app") as ia:
        sc.return_value = True
        em.return_value = True
        ia.return_value = True
        results = dispatch_alert(db_session, alert)
    # warning_and_above (server_chan) + all (in_app), NOT critical_only (email)
    assert len(results) == 2


def test_dispatch_info_only_in_app(db_session, setup_channels):
    """Info should ONLY go to 'all' filter channel."""
    alert = create_alert(db_session, severity="info", category="api",
                          message="Test info")
    db_session.flush()
    with patch("app.services.notification_service._send_server_chan") as sc, \
         patch("app.services.notification_service._send_email") as em, \
         patch("app.services.notification_service._send_in_app") as ia:
        sc.return_value = True
        em.return_value = True
        ia.return_value = True
        results = dispatch_alert(db_session, alert)
    assert len(results) == 1
    assert results[0].channel_type == "in_app"


def test_dispatch_failed_channel_records_error(db_session, setup_channels):
    """If channel fails, result includes error message."""
    alert = create_alert(db_session, severity="critical", category="data",
                          message="x")
    db_session.flush()
    with patch("app.services.notification_service._send_server_chan") as sc:
        sc.return_value = False
        with patch("app.services.notification_service._send_email") as em:
            em.return_value = True
            with patch("app.services.notification_service._send_in_app") as ia:
                ia.return_value = True
                results = dispatch_alert(db_session, alert)
    sc_result = next(r for r in results if r.channel_type == "server_chan")
    assert not sc_result.success
    assert sc_result.error_message is not None


def test_send_server_chan_calls_correct_url():
    with patch("app.services.notification_service.requests") as mock_req:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": 0}
        mock_req.post.return_value = mock_resp
        ok = _send_server_chan(
            sendkey="SCT123",
            title="Test Alert",
            content="Critical issue",
        )
        assert ok is True
        mock_req.post.assert_called_once()
        args, kwargs = mock_req.post.call_args
        assert "sendkey" in str(args) or "sendkey" in str(kwargs)


def test_send_dingtalk_webhook():
    with patch("app.services.notification_service.requests") as mock_req:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"errcode": 0}
        mock_req.post.return_value = mock_resp
        ok = _send_dingtalk_webhook(
            webhook_url="https://oapi.dingtalk.com/robot/send?access_token=xxx",
            title="Test", content="body",
        )
        assert ok is True
