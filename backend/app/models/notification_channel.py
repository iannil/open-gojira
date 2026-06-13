"""NotificationChannel — external push channels (server_chan / email / etc).

Filtered by severity: critical_only | warning_and_above | all.
Failed dispatches fall back to in_app (system_alerts).
"""
from datetime import datetime
from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base


class NotificationChannel(Base):
    __tablename__ = "notification_channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    """Unique channel name (e.g. 'server_chan_main')."""

    type: Mapped[str] = mapped_column(String, nullable=False)
    """in_app | server_chan | email | dingtalk_webhook | telegram_bot"""

    config_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    """Type-specific config:
    - server_chan: {sendkey}
    - email: {to, smtp_host, smtp_user, smtp_pass}
    - dingtalk_webhook: {webhook_url}
    - telegram_bot: {bot_token, chat_id}
    """

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    severity_filter: Mapped[str] = mapped_column(
        String, nullable=False, default="all"
    )
    """all | warning_and_above | critical_only"""

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
