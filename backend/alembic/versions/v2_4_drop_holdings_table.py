"""v2 (2026-06-26): drop the holdings table

Revision ID: v2_4_drop_holdings_table
Revises: v2_3_draft_phase5_fields
Create Date: 2026-06-26

Q2-A (paper-trading loop design): positions/P&L are derived from the trade
ledger (position_service); the Holding model is retired. This drops the now
unused `holdings` table from existing databases. Fresh deploys never create it
(the v2_baseline_squash create_all baseline no longer includes the model).

Guarded: only drops the table if it exists, so it is safe on fresh databases.
"""
from alembic import op
import sqlalchemy as sa


revision = "v2_4_drop_holdings_table"
down_revision = "v2_3_draft_phase5_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "holdings" in sa.inspect(bind).get_table_names():
        op.drop_table("holdings")


def downgrade() -> None:
    # One-way retirement: the Holding model no longer exists, so we cannot
    # faithfully recreate the table. No-op.
    pass
