"""add corp_actions table — corporate action event source

Revision ID: s4a_1_corp_actions
Revises: s3_2_data_freshness
Create Date: 2026-06-13 00:50:00

S4A.1: Event source for corporate actions affecting holdings.
- cash_dividend / stock_dividend / capitalization synced from Lixinger
  /cn/company/dividend endpoint.
- rights_issue requires manual entry (Lixinger /allotment is zombie).
- delist detected heuristically via company list diff.
- merger / code_change via manual or historyStockNames profile.

Unique constraint on (stock_code, ex_date, action_type, source) prevents
duplicate sync. processed_at IS NULL identifies pending actions for the
daily applier job (S4A.4).

Indexes:
- stock_code, ex_date, action_type, processed_at (single-column filters)
- (ex_date, processed_at) composite for daily "find pending up to today"
"""
revision = "s4a_1_corp_actions"
down_revision = "s3_2_data_freshness"
branch_labels = None
depends_on = None

import sqlalchemy as sa  # noqa: E402
from alembic import op  # noqa: E402


def upgrade():
    op.create_table(
        "corp_actions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "stock_code",
            sa.String,
            sa.ForeignKey("stocks.code"),
            nullable=False,
        ),
        sa.Column("ex_date", sa.Date, nullable=False),
        sa.Column("action_type", sa.String, nullable=False),
        sa.Column("params_json", sa.JSON, nullable=False),
        sa.Column(
            "source",
            sa.String,
            nullable=False,
            server_default="lixinger",
        ),
        sa.Column(
            "created_at",
            sa.DateTime,
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime, nullable=True),
        sa.Column(
            "applied_trade_id",
            sa.Integer,
            sa.ForeignKey("trades.id"),
            nullable=True,
        ),
        sa.Column("note", sa.Text, nullable=True),
        sa.UniqueConstraint(
            "stock_code",
            "ex_date",
            "action_type",
            "source",
            name="uq_corp_actions_natural_key",
        ),
    )
    op.create_index("ix_corp_actions_stock_code", "corp_actions", ["stock_code"])
    op.create_index("ix_corp_actions_ex_date", "corp_actions", ["ex_date"])
    op.create_index("ix_corp_actions_action_type", "corp_actions", ["action_type"])
    op.create_index("ix_corp_actions_processed_at", "corp_actions", ["processed_at"])
    op.create_index(
        "ix_corp_actions_pending", "corp_actions", ["ex_date", "processed_at"]
    )


def downgrade():
    op.drop_index("ix_corp_actions_pending", table_name="corp_actions")
    op.drop_index("ix_corp_actions_processed_at", table_name="corp_actions")
    op.drop_index("ix_corp_actions_action_type", table_name="corp_actions")
    op.drop_index("ix_corp_actions_ex_date", table_name="corp_actions")
    op.drop_index("ix_corp_actions_stock_code", table_name="corp_actions")
    op.drop_table("corp_actions")
