"""add stock trading fields: listing_status / exchange / fs_table_type / ipo_date

Revision ID: s1_1_stock_fields
Revises: 3c5b80889c29
Create Date: 2026-06-12 20:00:00

S1.1: store raw Lixinger /cn/company trading-status fields. These replace
planned derived fields (board / is_st / is_suspended) with their source values,
which are more reliable than inferring from code prefix or name matching.

All nullable=True so historical rows (and any pre-migration manual entries)
remain valid. Indexes added on listing_status and exchange (high-frequency
filter columns for universe screening); fs_table_type is low-cardinality so
no index.
"""
revision = "s1_1_stock_fields"
down_revision = "3c5b80889c29"
branch_labels = None
depends_on = None

from alembic import op  # noqa: E402
import sqlalchemy as sa  # noqa: E402


def upgrade():
    op.add_column("stocks", sa.Column("listing_status", sa.String(), nullable=True))
    op.add_column("stocks", sa.Column("exchange", sa.String(), nullable=True))
    op.add_column("stocks", sa.Column("fs_table_type", sa.String(), nullable=True))
    op.add_column("stocks", sa.Column("ipo_date", sa.Date(), nullable=True))
    op.create_index("ix_stocks_listing_status", "stocks", ["listing_status"])
    op.create_index("ix_stocks_exchange", "stocks", ["exchange"])


def downgrade():
    op.drop_index("ix_stocks_exchange", table_name="stocks")
    op.drop_index("ix_stocks_listing_status", table_name="stocks")
    op.drop_column("stocks", "ipo_date")
    op.drop_column("stocks", "fs_table_type")
    op.drop_column("stocks", "exchange")
    op.drop_column("stocks", "listing_status")
