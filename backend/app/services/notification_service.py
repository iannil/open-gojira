"""Notification dispatch — push alerts to external channels.

Channel types:
- in_app: writes to system_alerts (always succeeds, no network)
- server_chan: 微信推送 (https://sct.ftqq.com/)
- email: SMTP (deferred to v2; scaffold only)
- dingtalk_webhook: 钉钉机器人
- telegram_bot: TG bot (scaffold)

Severity filter routing:
- all: receives info/warning/critical
- warning_and_above: receives warning + critical
- critical_only: receives critical only
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.notification_channel import NotificationChannel
from app.models.system_alert import SystemAlert
from app.core.datetime_utils import now


logger = logging.getLogger(__name__)


def _utcnow_naive() -> datetime:
    return now()


def _matches_severity(channel_severity: str, alert_severity: str) -> bool:
    """Does the channel want alerts of this severity?"""
    if channel_severity == "all":
        return True
    if channel_severity == "warning_and_above":
        return alert_severity in ("warning", "critical")
    if channel_severity == "critical_only":
        return alert_severity == "critical"
    return False  # unknown filter


@dataclass
class DispatchResult:
    channel_id: int
    channel_name: str
    channel_type: str
    success: bool
    error_message: str | None = None


# --- Per-type senders (module-level so they can be patched in tests) ---


def _send_in_app(db: Session, alert: SystemAlert) -> bool:
    """No-op: alert already persisted to system_alerts table."""
    return True


def _send_server_chan(sendkey: str, title: str, content: str) -> bool:
    try:
        resp = requests.post(
            f"https://sctapi.ftqq.com/{sendkey}.send",
            data={
                "sendkey": sendkey,
                "title": title[:32],
                "desp": content[:32 * 1024],
            },
            timeout=10,
        )
        if resp.status_code != 200:
            logger.warning("server_chan HTTP %s", resp.status_code)
            return False
        data = resp.json()
        return data.get("code", -1) == 0
    except Exception as e:
        logger.error("server_chan failed: %s", e)
        return False


def _send_dingtalk_webhook(webhook_url: str, title: str, content: str) -> bool:
    try:
        resp = requests.post(
            webhook_url,
            json={
                "msgtype": "markdown",
                "markdown": {
                    "title": title,
                    "text": f"## {title}\n\n{content}",
                },
            },
            timeout=10,
        )
        if resp.status_code != 200:
            return False
        return resp.json().get("errcode", -1) == 0
    except Exception as e:
        logger.error("dingtalk failed: %s", e)
        return False


def _send_email(smtp_config: dict, subject: str, body: str) -> bool:
    """Scaffold — email implementation deferred to v2."""
    logger.info("Email would send to %s: %s", smtp_config.get("to"), subject)
    return False  # not implemented yet


def _build_title(alert: SystemAlert) -> str:
    return f"[{alert.severity.upper()}] {alert.category}: {alert.message[:50]}"


def _build_content(alert: SystemAlert) -> str:
    return f"{alert.message}\n\nDetail: {alert.detail_json}"


# Channel-type dispatch table. Each callable takes (db, channel, alert)
# and returns True on success, False on failure.  The per-type senders
# are looked up by name (so tests can patch them at module level).
_SENDERS: dict[str, Callable[[Session, NotificationChannel, SystemAlert], bool]] = {
    "in_app": lambda db, ch, alert: _send_in_app(db, alert),
    "server_chan": lambda db, ch, alert: _send_server_chan(
        sendkey=ch.config_json.get("sendkey", "") if ch.config_json else "",
        title=_build_title(alert),
        content=_build_content(alert),
    ),
    "dingtalk_webhook": lambda db, ch, alert: _send_dingtalk_webhook(
        webhook_url=ch.config_json.get("webhook_url", "") if ch.config_json else "",
        title=f"[{alert.severity.upper()}] {alert.category}",
        content=f"{alert.message}\n\n```json\n{alert.detail_json}\n```",
    ),
    "email": lambda db, ch, alert: _send_email(
        smtp_config=ch.config_json or {},
        subject=f"[{alert.severity.upper()}] {alert.message[:50]}",
        body=str(alert.detail_json),
    ),
}


def send_to_channel(
    db: Session, channel: NotificationChannel, alert: SystemAlert
) -> DispatchResult:
    """Send one alert to one channel."""
    sender = _SENDERS.get(channel.type)
    if not sender:
        return DispatchResult(
            channel_id=channel.id,
            channel_name=channel.name,
            channel_type=channel.type,
            success=False,
            error_message=f"Unknown channel type: {channel.type}",
        )
    try:
        ok = sender(db, channel, alert)
        return DispatchResult(
            channel_id=channel.id,
            channel_name=channel.name,
            channel_type=channel.type,
            success=bool(ok),
            error_message=None if ok else "Sender returned False",
        )
    except Exception as e:
        return DispatchResult(
            channel_id=channel.id,
            channel_name=channel.name,
            channel_type=channel.type,
            success=False,
            error_message=str(e)[:200],
        )


def dispatch_alert(db: Session, alert: SystemAlert) -> list[DispatchResult]:
    """Push alert to all enabled channels matching its severity."""
    channels = db.execute(
        select(NotificationChannel).where(NotificationChannel.enabled == True)  # noqa: E712
    ).scalars().all()

    results: list[DispatchResult] = []
    for ch in channels:
        if not _matches_severity(ch.severity_filter, alert.severity):
            continue
        result = send_to_channel(db, ch, alert)
        results.append(result)
        if not result.success and ch.type != "in_app":
            logger.warning(
                "Channel %s failed: %s", ch.name, result.error_message
            )

    return results


# --- CRUD ---


def list_channels(
    db: Session, enabled_only: bool = False
) -> list[NotificationChannel]:
    stmt = select(NotificationChannel).order_by(NotificationChannel.name)
    if enabled_only:
        stmt = stmt.where(NotificationChannel.enabled == True)  # noqa: E712
    return list(db.execute(stmt).scalars().all())


def create_channel(
    db: Session,
    *,
    name: str,
    type: str,
    config: dict,
    severity_filter: str = "all",
    enabled: bool = True,
) -> NotificationChannel:
    ch = NotificationChannel(
        name=name,
        type=type,
        config_json=config,
        severity_filter=severity_filter,
        enabled=enabled,
    )
    db.add(ch)
    db.flush()
    return ch


def update_channel(
    db: Session, channel_id: int, updates: dict
) -> NotificationChannel | None:
    ch = db.get(NotificationChannel, channel_id)
    if not ch:
        return None
    for k, v in updates.items():
        if hasattr(ch, k):
            setattr(ch, k, v)
    ch.updated_at = _utcnow_naive()
    db.flush()
    return ch


def delete_channel(db: Session, channel_id: int) -> bool:
    ch = db.get(NotificationChannel, channel_id)
    if not ch:
        return False
    db.delete(ch)
    db.flush()
    return True
