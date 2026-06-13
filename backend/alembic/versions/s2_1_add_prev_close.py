"""add stock.prev_close field

Revision ID: s2_1_prev_close
Revises: s1_8_migrate_data
Create Date: 2026-06-12 23:00:00

S2.1: Add prev_close column to stocks table. Populated daily by the
daily_prev_close_sync scheduler job (mon-fri 17:20 Asia/Shanghai) from
the latest K-line close. Used by S2.2 price_validator for 涨跌停
(price band) calculation.

Nullable because:
- New stocks have no K-line history yet
- Stocks with no recent trades return empty kline windows
- Migration must not fail on stocks without data
"""
revision = "s2_1_prev_close"
down_revision = "s1_8_migrate_data"
branch_labels = None
depends_on = None

import sqlalchemy as sa
from alembic import op


def upgrade():
    op.add_column("stocks", sa.Column("prev_close", sa.Float(), nullable=True))


def downgrade():
    op.drop_column("stocks", "prev_close")
