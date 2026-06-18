"""Audit F12 (2026-06-18): flip plans.disable_in_circle_filter default to True

Revision ID: s10_1_in_circle_filter_default_off
Revises: s9_2_draft_plan_id_nullable
Create Date: 2026-06-18

Drift found in 2026-06-18 feature audit (docs/progress/2026-06-18-feature-audit-drift-findings.md F12):

  Batch 5 M2 introduced `plans.disable_in_circle_filter BOOLEAN DEFAULT FALSE`,
  meaning the in_circle filter was ON by default. Combined with `Stock.in_circle`
  being unfilled on every stock (0/5626 = TRUE in production DB), plan_runner's
  `_filter_out_of_circle` returned `kept=[], dropped=5626` for all plans,
  producing 0 candidates even after fixing F4-F8.

Fix: flip the default to TRUE (filter OFF by default). Users who actually mark
stocks `in_circle=True` can opt back in by setting `disable_in_circle_filter=False`
on specific plans.

This migration:
  1. Changes server_default from '0' to '1'
  2. Backfills existing rows: UPDATE plans SET disable_in_circle_filter=1
     WHERE disable_in_circle_filter=0 (overrides any prior user choice —
     intentional, since prior default-False state was a production-breaking bug)
"""
revision = "s10_1_in_circle_filter_default_off"
down_revision = "s9_2_draft_plan_id_nullable"
branch_labels = None
depends_on = None

import sqlalchemy as sa  # noqa: E402
from alembic import op  # noqa: E402


def upgrade():
    # 1. Flip server_default so new plans get disable_in_circle_filter=TRUE
    with op.batch_alter_table("plans") as batch_op:
        batch_op.alter_column(
            "disable_in_circle_filter",
            existing_type=sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        )

    # 2. Backfill existing rows — every existing plan flips to filter-OFF
    op.execute("UPDATE plans SET disable_in_circle_filter = 1")


def downgrade():
    with op.batch_alter_table("plans") as batch_op:
        batch_op.alter_column(
            "disable_in_circle_filter",
            existing_type=sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        )
