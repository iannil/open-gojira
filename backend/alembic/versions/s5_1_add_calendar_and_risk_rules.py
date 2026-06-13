"""add trading_calendar + holding_risk_rules tables

Revision ID: s5_1_calendar_risk
Revises: s4c_1_backtest_runs
Create Date: 2026-06-13 10:05:00

S5.1: Two foundations for S5 intraday monitoring.

trading_calendar:
- Pre-populated with 2025-2027 A-share holidays (元旦 / 春节 / 清明 /
  劳动 / 端午 / 国庆).
- is_trading_day() in service layer falls back to weekday check for
  unseeded dates, so function works before seeding is run.
- Updated yearly as State Council publishes the schedule.

holding_risk_rules:
- One row per stock_code (unique) since holdings are derived from
  trades, not stored per Holding row.
- stop_loss_type: pct_from_cost | fixed_price | trailing.
- peak_price used by trailing mode (highest since rule active).
- triggered_at + trigger_reason for audit trail.
- Index on triggered_at for "show me recently triggered" queries.
"""
revision = "s5_1_calendar_risk"
down_revision = "s4c_1_backtest_runs"
branch_labels = None
depends_on = None

import sqlalchemy as sa  # noqa: E402
from alembic import op  # noqa: E402


def upgrade():
    op.create_table(
        "trading_calendar",
        sa.Column("date", sa.Date, primary_key=True),
        sa.Column("is_trading_day", sa.Boolean, nullable=False),
        sa.Column("holiday_name", sa.String, nullable=True),
    )

    op.create_table(
        "holding_risk_rules",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "stock_code",
            sa.String,
            sa.ForeignKey("stocks.code"),
            nullable=False,
            unique=True,
        ),
        sa.Column("stop_loss_pct", sa.Float, nullable=True),
        sa.Column(
            "stop_loss_type",
            sa.String,
            nullable=False,
            server_default="pct_from_cost",
        ),
        sa.Column("take_profit_pct", sa.Float, nullable=True),
        sa.Column(
            "take_profit_type",
            sa.String,
            nullable=False,
            server_default="pct_from_cost",
        ),
        sa.Column("peak_price", sa.Float, nullable=True),
        sa.Column(
            "enabled", sa.Boolean, nullable=False, server_default=sa.text("1")
        ),
        sa.Column("triggered_at", sa.DateTime, nullable=True),
        sa.Column("trigger_reason", sa.String, nullable=True),
        sa.Column(
            "created_at", sa.DateTime, server_default=sa.func.now()
        ),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )
    op.create_index(
        "ix_holding_risk_rules_stock_code",
        "holding_risk_rules",
        ["stock_code"],
    )
    op.create_index(
        "ix_holding_risk_rules_triggered_at",
        "holding_risk_rules",
        ["triggered_at"],
    )


def downgrade():
    op.drop_index(
        "ix_holding_risk_rules_triggered_at", table_name="holding_risk_rules"
    )
    op.drop_index(
        "ix_holding_risk_rules_stock_code", table_name="holding_risk_rules"
    )
    op.drop_table("holding_risk_rules")
    op.drop_table("trading_calendar")
