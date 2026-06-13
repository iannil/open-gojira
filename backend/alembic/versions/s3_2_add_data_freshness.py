"""add data_freshness table

Revision ID: s3_2_data_freshness
Revises: s3_1_system_alerts
Create Date: 2026-06-13 00:30:00

S3.2: Per-category data freshness tracking. One row per data category
(stocks / valuation / kline / financial / dividend / corp_action)
recording last_synced_at / last_success_at / last_record_count / last_error.

plan_runner calls assert_fresh_enough() before generating drafts to
refuse running on stale data. Pipelines call record_sync_success /
record_sync_failure on completion.

Unique index on category — each category has exactly one row.
"""
revision = "s3_2_data_freshness"
down_revision = "s3_1_system_alerts"
branch_labels = None
depends_on = None

import sqlalchemy as sa
from alembic import op


def upgrade():
    op.create_table(
        "data_freshness",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("category", sa.String, nullable=False),
        sa.Column("last_synced_at", sa.DateTime, nullable=True),
        sa.Column("last_success_at", sa.DateTime, nullable=True),
        sa.Column("last_record_count", sa.Integer, nullable=True),
        sa.Column("last_error", sa.String, nullable=True),
    )
    op.create_index(
        "ix_data_freshness_category",
        "data_freshness",
        ["category"],
        unique=True,
    )


def downgrade():
    op.drop_index("ix_data_freshness_category", table_name="data_freshness")
    op.drop_table("data_freshness")
