"""add notification_channels table

Revision ID: s5_2_notifications
Revises: s5_1_calendar_risk
Create Date: 2026-06-13 10:15:00

S5.2: External push channels for system_alerts.

Channel types:
- in_app: no-op (alert already in system_alerts; default channel seeded)
- server_chan: WeChat push via sctapi.ftqq.com
- email: SMTP (scaffold; deferred to v2)
- dingtalk_webhook: 钉钉 robot
- telegram_bot: TG bot (scaffold)

Severity filter routing (per channel):
- all: receives info / warning / critical
- warning_and_above: warning + critical
- critical_only: critical only

On upgrade, seeds one default 'in_app_default' channel so dispatch_alert
always has somewhere to land (safety net).
"""
revision = "s5_2_notifications"
down_revision = "s5_1_calendar_risk"
branch_labels = None
depends_on = None

import sqlalchemy as sa  # noqa: E402
from alembic import op  # noqa: E402


def upgrade():
    op.create_table(
        "notification_channels",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String, nullable=False, unique=True),
        sa.Column("type", sa.String, nullable=False),
        sa.Column(
            "config_json",
            sa.JSON,
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "enabled", sa.Boolean, nullable=False, server_default=sa.text("1")
        ),
        sa.Column(
            "severity_filter",
            sa.String,
            nullable=False,
            server_default="all",
        ),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )
    op.create_index(
        "ix_notification_channels_name",
        "notification_channels",
        ["name"],
    )

    # Seed default in_app channel — dispatch always has somewhere to land
    op.execute(
        "INSERT INTO notification_channels "
        "(name, type, config_json, enabled, severity_filter) "
        "VALUES ('in_app_default', 'in_app', '{}', 1, 'all')"
    )


def downgrade():
    op.drop_index(
        "ix_notification_channels_name", table_name="notification_channels"
    )
    op.drop_table("notification_channels")
