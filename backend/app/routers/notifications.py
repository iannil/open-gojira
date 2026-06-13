"""Notifications API — channel CRUD + test dispatch (S5.4).

Exposes notification_channel management so users can configure push
destinations for system_alerts: server_chan (WeChat), email, dingtalk
webhook, telegram bot.

The dispatch logic itself lives in notification_service.dispatch_alert,
called from the scheduler's intraday_price_poll job when stop-loss /
take-profit events fire.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.notification_channel import NotificationChannel
from app.services.notification_service import (
    create_channel,
    delete_channel,
    list_channels,
    send_to_channel,
    update_channel,
)
from app.services.system_alert_service import create_alert

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


# ── Schemas ───────────────────────────────────────────────────────────────


class ChannelResponse(BaseModel):
    id: int
    name: str
    type: str
    config_json: dict
    enabled: bool
    severity_filter: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ChannelCreate(BaseModel):
    name: str
    type: str  # in_app | server_chan | email | dingtalk_webhook | telegram_bot
    config_json: dict
    enabled: bool = True
    severity_filter: str = "all"  # all | warning_and_above | critical_only


class ChannelUpdate(BaseModel):
    config_json: dict | None = None
    enabled: bool | None = None
    severity_filter: str | None = None


class TestResult(BaseModel):
    success: bool
    error: str | None = None


# ── Endpoints ─────────────────────────────────────────────────────────────


@router.get("/channels", response_model=list[ChannelResponse])
def api_list_channels(
    enabled_only: bool = False, db: Session = Depends(get_db)
) -> list[NotificationChannel]:
    return list_channels(db, enabled_only=enabled_only)


@router.post("/channels", response_model=ChannelResponse, status_code=201)
def api_create_channel(
    payload: ChannelCreate, db: Session = Depends(get_db)
) -> NotificationChannel:
    ch = create_channel(
        db,
        name=payload.name,
        type=payload.type,
        config=payload.config_json,
        severity_filter=payload.severity_filter,
        enabled=payload.enabled,
    )
    db.commit()
    db.refresh(ch)
    return ch


@router.patch("/channels/{channel_id}", response_model=ChannelResponse)
def api_update_channel(
    channel_id: int, payload: ChannelUpdate, db: Session = Depends(get_db)
) -> NotificationChannel:
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    ch = update_channel(db, channel_id, updates)
    if not ch:
        raise HTTPException(404, f"channel {channel_id} not found")
    db.commit()
    db.refresh(ch)
    return ch


@router.delete("/channels/{channel_id}", status_code=204)
def api_delete_channel(channel_id: int, db: Session = Depends(get_db)) -> None:
    if not delete_channel(db, channel_id):
        raise HTTPException(404, f"channel {channel_id} not found")
    db.commit()


@router.post("/test/{channel_id}", response_model=TestResult)
def api_test_channel(
    channel_id: int, db: Session = Depends(get_db)
) -> TestResult:
    """Send a test alert through this channel.

    Creates an info-severity SystemAlert, then dispatches it to the
    single channel (bypassing the severity filter so the user can verify
    delivery even on critical_only channels).
    """
    ch = db.get(NotificationChannel, channel_id)
    if not ch:
        raise HTTPException(404, f"channel {channel_id} not found")
    alert = create_alert(
        db,
        severity="info",
        category="api",
        message=f"Test notification from channel '{ch.name}'",
        detail={"test": True, "channel_id": ch.id},
    )
    db.flush()
    result = send_to_channel(db, ch, alert)
    db.commit()
    return TestResult(success=result.success, error=result.error_message)
