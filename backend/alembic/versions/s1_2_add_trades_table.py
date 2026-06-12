"""add trades table — immutable event source

Revision ID: s1_2_trades
Revises: s1_1_stock_fields
Create Date: 2026-06-12 20:30:00

S1.2: foundation table for production-grade position tracking. Trades record
facts (price/qty/fees at filled_at); holdings, cash balance, and P&L are all
derived views in later tasks.

Design:
- Immutable: never UPDATE/DELETE; reverse via reversed_by_trade_id.
- Sides: BUY/SELL/DIVIDEND/CORP_ACTION/REVERSAL with sign conventions.
- Sources: manual/csv_import/broker_api/corp_action/migration/reversal.
- Indexes: stock_code+filled_at composite (range scans), source (filtering),
  plus single-column indexes on stock_code, side, filled_at.
"""
revision = "s1_2_trades"
down_revision = "s1_1_stock_fields"
branch_labels = None
depends_on = None

import sqlalchemy as sa  # noqa: E402
from alembic import op  # noqa: E402


def upgrade():
    op.create_table(
        "trades",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "stock_code",
            sa.String,
            sa.ForeignKey("stocks.code"),
            nullable=False,
        ),
        sa.Column("side", sa.String, nullable=False),
        sa.Column("price", sa.Float, nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("filled_at", sa.DateTime, nullable=False),
        sa.Column("commission", sa.Float, nullable=False, server_default="0"),
        sa.Column("stamp_duty", sa.Float, nullable=False, server_default="0"),
        sa.Column("transfer_fee", sa.Float, nullable=False, server_default="0"),
        sa.Column("total_value", sa.Float, nullable=False),
        sa.Column("source", sa.String, nullable=False, server_default="manual"),
        sa.Column("source_ref", sa.String, nullable=True),
        sa.Column("fee_source", sa.String, nullable=False, server_default="auto"),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column(
            "reversed_by_trade_id",
            sa.Integer,
            sa.ForeignKey("trades.id"),
            nullable=True,
        ),
    )
    op.create_index("ix_trades_stock_code", "trades", ["stock_code"])
    op.create_index("ix_trades_side", "trades", ["side"])
    op.create_index("ix_trades_filled_at", "trades", ["filled_at"])
    op.create_index("ix_trades_code_filled", "trades", ["stock_code", "filled_at"])
    op.create_index("ix_trades_source", "trades", ["source"])


def downgrade():
    op.drop_index("ix_trades_source", table_name="trades")
    op.drop_index("ix_trades_code_filled", table_name="trades")
    op.drop_index("ix_trades_filled_at", table_name="trades")
    op.drop_index("ix_trades_side", table_name="trades")
    op.drop_index("ix_trades_stock_code", table_name="trades")
    op.drop_table("trades")
