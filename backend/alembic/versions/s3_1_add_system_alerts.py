"""add system_alerts table

Revision ID: s3_1_system_alerts
Revises: s2_5_draft_qty
Create Date: 2026-06-13 00:20:00

S3.1: Unified infrastructure-level alert table. Records system problems
(Lixinger API failures, data staleness, sanity violations, scheduler
crashes, token expiry) for the UI to surface as a top red banner.

Distinct from business `alert_events` table (price/thesis breaches):
- system_alerts  → infrastructure / pipeline health
- alert_events   → market / portfolio triggers

Indexes on severity/category/created_at/resolved_at to support:
- UI badge: COUNT(*) WHERE severity='critical' AND resolved_at IS NULL
- Filtering by category for recovery sweep
- Time-ordered listing
"""
revision = "s3_1_system_alerts"
down_revision = "s2_5_draft_qty"
branch_labels = None
depends_on = None

import sqlalchemy as sa
from alembic import op


def upgrade():
    op.create_table(
        "system_alerts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("severity", sa.String, nullable=False),
        sa.Column("category", sa.String, nullable=False),
        sa.Column("message", sa.String, nullable=False),
        sa.Column("detail_json", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime, nullable=True),
        sa.Column("resolved_by", sa.String, nullable=True),
    )
    op.create_index("ix_system_alerts_severity", "system_alerts", ["severity"])
    op.create_index("ix_system_alerts_category", "system_alerts", ["category"])
    op.create_index("ix_system_alerts_created_at", "system_alerts", ["created_at"])
    op.create_index("ix_system_alerts_resolved_at", "system_alerts", ["resolved_at"])


def downgrade():
    op.drop_index("ix_system_alerts_resolved_at", table_name="system_alerts")
    op.drop_index("ix_system_alerts_created_at", table_name="system_alerts")
    op.drop_index("ix_system_alerts_category", table_name="system_alerts")
    op.drop_index("ix_system_alerts_severity", table_name="system_alerts")
    op.drop_table("system_alerts")
