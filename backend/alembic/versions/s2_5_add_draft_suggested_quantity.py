"""add draft.suggested_quantity field

Revision ID: s2_5_draft_qty
Revises: s2_1_prev_close
Create Date: 2026-06-12 23:30:00

S2.5: Add suggested_quantity column to drafts table. Populated by plan_runner
when generating BUY drafts (via position_sizing_service.compute_buy_quantity)
to surface an actionable "建议买入 N 股" rather than just "10%".

Nullable because:
- SELL drafts have no concept of buy quantity
- BUY drafts may have None when position sizing fails or NAV is unknown
- Migration must not fail on drafts already persisted without this field
"""
revision = "s2_5_draft_qty"
down_revision = "s2_1_prev_close"
branch_labels = None
depends_on = None

import sqlalchemy as sa
from alembic import op


def upgrade():
    op.add_column("drafts", sa.Column("suggested_quantity", sa.Integer, nullable=True))


def downgrade():
    op.drop_column("drafts", "suggested_quantity")
