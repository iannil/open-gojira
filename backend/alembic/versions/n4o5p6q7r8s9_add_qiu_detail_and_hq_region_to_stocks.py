"""add qiu_detail_json and hq_region to stocks

Revision ID: n4o5p6q7r8s9
Revises: c61ab22a968f
Create Date: 2026-06-06
"""

from alembic import op
import sqlalchemy as sa

revision = "n4o5p6q7r8s9"
down_revision = "c61ab22a968f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = {c["name"] for c in insp.get_columns("stocks")}
    if "qiu_detail_json" not in cols:
        op.add_column("stocks", sa.Column("qiu_detail_json", sa.Text(), nullable=True))
    if "hq_region" not in cols:
        op.add_column("stocks", sa.Column("hq_region", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("stocks", "hq_region")
    op.drop_column("stocks", "qiu_detail_json")
