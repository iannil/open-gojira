"""Notification service — v2 in-app only.

v2 (decision 19 / v2-implementation-plan.md): external notification *channels*
(email / DingTalk / ServerChan) were dropped. Alerts now surface in-app as
``SystemAlert`` rows, created by ``system_alert_service``.

``dispatch_alert`` is retained as a no-op so existing callers (scheduler
job-failure path, event handlers) need no changes — the in-app alert they pass
in has already been persisted, and there are no external channels to push to.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.system_alert import SystemAlert


def dispatch_alert(db: Session, alert: SystemAlert) -> list:
    """v2 no-op dispatch.

    The in-app ``SystemAlert`` is already persisted by the caller
    (``system_alert_service.create_alert``). External channels were removed in
    v2, so there is nothing to dispatch. Returns an empty result list.
    """
    return []
