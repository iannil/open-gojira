"""add backtest_runs table

Revision ID: s4c_1_backtest_runs
Revises: s4b_1_historical
Create Date: 2026-06-13 09:35:00

S4C.1: BacktestRun — one row per backtest execution.

Lifecycle: pending → running → completed | failed

config_json (immutable input, NOT NULL): strategy_ids, plan_id,
start_date, end_date, initial_capital, slippage_bps, lot_size, etc.

result_json (filled on completion): metrics (cagr/sharpe/maxDD/win_rate),
equity_curve, monthly_returns, trades_count, signals_count,
benchmark_comparison.

Indexes:
- status: find pending/running runs (dashboard polling).
- completed_at: list recent finished runs.

API endpoints added in S4C.4.
"""
revision = "s4c_1_backtest_runs"
down_revision = "s4b_1_historical"
branch_labels = None
depends_on = None

import sqlalchemy as sa  # noqa: E402
from alembic import op  # noqa: E402


def upgrade():
    op.create_table(
        "backtest_runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("config_json", sa.JSON, nullable=False),
        sa.Column(
            "status", sa.String, nullable=False, server_default="pending"
        ),
        sa.Column("result_json", sa.JSON, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("completed_at", sa.DateTime, nullable=True),
    )
    op.create_index(
        "ix_backtest_runs_status", "backtest_runs", ["status"]
    )
    op.create_index(
        "ix_backtest_runs_completed_at", "backtest_runs", ["completed_at"]
    )


def downgrade():
    op.drop_index(
        "ix_backtest_runs_completed_at", table_name="backtest_runs"
    )
    op.drop_index("ix_backtest_runs_status", table_name="backtest_runs")
    op.drop_table("backtest_runs")
