"""add broker_fee_configs table

Revision ID: s1_4_fee_configs
Revises: s1_3_cash
Create Date: 2026-06-12 21:30:00

S1.4: broker fee configuration table — commission / stamp duty / transfer
fee rates with effective_from for historical lookups.

- One row per (broker_name, effective_from) tuple.
- fee_calculator_service picks the config whose effective_from is the
  latest one <= trade.filled_at.
- Default config seeded by builtin_seeder on startup, NOT here (seeder
  is idempotent and Python-typed).
"""
revision = "s1_4_fee_configs"
down_revision = "s1_3_cash"
branch_labels = None
depends_on = None

import sqlalchemy as sa  # noqa: E402
from alembic import op  # noqa: E402


def upgrade():
    op.create_table(
        "broker_fee_configs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("broker_name", sa.String, nullable=False),
        sa.Column("commission_rate", sa.Float, nullable=False),
        sa.Column("commission_min", sa.Float, nullable=False, server_default="5.0"),
        sa.Column("stamp_duty_rate", sa.Float, nullable=False),
        sa.Column("transfer_fee_rate", sa.Float, nullable=False),
        sa.Column("effective_from", sa.Date, nullable=False),
        sa.Column(
            "is_active", sa.Boolean, nullable=False, server_default=sa.text("1")
        ),
    )
    op.create_index(
        "ix_broker_fee_configs_broker_name",
        "broker_fee_configs",
        ["broker_name"],
    )
    op.create_index(
        "ix_broker_fee_configs_effective_from",
        "broker_fee_configs",
        ["effective_from"],
    )


def downgrade():
    op.drop_index(
        "ix_broker_fee_configs_effective_from", table_name="broker_fee_configs"
    )
    op.drop_index(
        "ix_broker_fee_configs_broker_name", table_name="broker_fee_configs"
    )
    op.drop_table("broker_fee_configs")
