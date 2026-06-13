"""add cash_balance + cash_adjustments tables

Revision ID: s1_3_cash
Revises: s1_2_trades
Create Date: 2026-06-12 21:00:00

S1.3: cash management tables.

- cash_balance: singleton row (id=1) tracking current cash position.
  Updated atomically with each trade write and each cash_adjustment write.
  Includes last_trade_id / last_adjustment_id soft FKs for audit trace.
- cash_adjustments: immutable log of non-trade cash flows (deposits,
  withdrawals, dividend receipts outside trade stream, corrections).
  Indexed on happened_at for time-range queries.

Migration inserts the singleton row at id=1 with balance=0. Initial
capital will be set by user via UI (S1.9 cash router) or seeded via
the S1.8 data migration script.
"""
revision = "s1_3_cash"
down_revision = "s1_2_trades"
branch_labels = None
depends_on = None

import sqlalchemy as sa  # noqa: E402
from alembic import op  # noqa: E402


def upgrade():
    op.create_table(
        "cash_balance",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("balance", sa.Float, nullable=False, server_default="0"),
        sa.Column(
            "as_of_at", sa.DateTime, server_default=sa.func.now(), nullable=False
        ),
        sa.Column("last_trade_id", sa.Integer, nullable=True),
        sa.Column("last_adjustment_id", sa.Integer, nullable=True),
    )
    # Seed the singleton row. Initial capital will be set later via
    # UI (S1.9) or the S1.8 data migration script.
    op.execute("INSERT INTO cash_balance (id, balance) VALUES (1, 0.0)")

    op.create_table(
        "cash_adjustments",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("happened_at", sa.DateTime, nullable=False),
        sa.Column("reason", sa.String, nullable=False),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_cash_adjustments_happened_at", "cash_adjustments", ["happened_at"]
    )


def downgrade():
    op.drop_index("ix_cash_adjustments_happened_at", table_name="cash_adjustments")
    op.drop_table("cash_adjustments")
    op.drop_table("cash_balance")
