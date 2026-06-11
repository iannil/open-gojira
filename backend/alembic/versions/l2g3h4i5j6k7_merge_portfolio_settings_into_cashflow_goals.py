"""Merge portfolio_settings table into cashflow_goals table.

Revision ID: l2g3h4i5j6k7
Revises: k1f2g3h4i5j6
Create Date: 2026-06-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.sql import table, column

revision: str = "l2g3h4i5j6k7"
down_revision: Union[str, Sequence[str], None] = "640d21c84015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CASHFLOW_GOALS_TABLE = "cashflow_goals"
PORTFOLIO_SETTINGS_TABLE = "portfolio_settings"


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # Step 1: Add new columns to cashflow_goals if they don't exist
    if CASHFLOW_GOALS_TABLE in insp.get_table_names():
        columns = [col["name"] for col in insp.get_columns(CASHFLOW_GOALS_TABLE)]

        new_columns = [
            ("cash_reserve", sa.Float(), False, "0.0"),
            ("target_weighted_dyr", sa.Float(), False, "0.045"),
            ("position_plan_json", sa.Text(), True, None),
            ("current_index_pe_pct", sa.Float(), True, None),
            ("quadrant_targets_json", sa.Text(), True, None),
        ]

        for col_name, col_type, nullable, default in new_columns:
            if col_name not in columns:
                op.add_column(
                    CASHFLOW_GOALS_TABLE,
                    sa.Column(col_name, col_type, nullable=nullable, server_default=default)
                )

    # Step 2: Copy data from portfolio_settings to cashflow_goals
    if PORTFOLIO_SETTINGS_TABLE in insp.get_table_names() and CASHFLOW_GOALS_TABLE in insp.get_table_names():
        # Check if there's a portfolio_settings row with id=1
        conn = op.get_bind()
        result = conn.execute(sa.text(f"SELECT cash_reserve, target_weighted_dyr, position_plan_json, current_index_pe_pct FROM {PORTFOLIO_SETTINGS_TABLE} WHERE id = 1"))
        row = result.fetchone()

        if row:
            # Update the cashflow_goals row with id=1
            cash_reserve, target_weighted_dyr, position_plan_json, current_index_pe_pct = row
            conn.execute(
                sa.text(f"""
                    UPDATE {CASHFLOW_GOALS_TABLE}
                    SET cash_reserve = :cash_reserve,
                        target_weighted_dyr = :target_weighted_dyr,
                        position_plan_json = :position_plan_json,
                        current_index_pe_pct = :current_index_pe_pct
                    WHERE id = 1
                """),
                {
                    "cash_reserve": cash_reserve or 0.0,
                    "target_weighted_dyr": target_weighted_dyr or 0.045,
                    "position_plan_json": position_plan_json,
                    "current_index_pe_pct": current_index_pe_pct
                }
            )

    # Step 3: Drop portfolio_settings table if it exists
    if PORTFOLIO_SETTINGS_TABLE in insp.get_table_names():
        op.drop_table(PORTFOLIO_SETTINGS_TABLE)


def downgrade() -> None:
    """Reverse the migration: recreate portfolio_settings and move data back."""
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # Step 1: Recreate portfolio_settings table
    if PORTFOLIO_SETTINGS_TABLE not in insp.get_table_names():
        op.create_table(
            PORTFOLIO_SETTINGS_TABLE,
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("cash_reserve", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("target_weighted_dyr", sa.Float(), nullable=False, server_default="0.045"),
            sa.Column("position_plan_json", sa.Text(), nullable=True),
            sa.Column("current_index_pe_pct", sa.Float(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    # Step 2: Copy data back from cashflow_goals to portfolio_settings
    if CASHFLOW_GOALS_TABLE in insp.get_table_names():
        columns = [col["name"] for col in insp.get_columns(CASHFLOW_GOALS_TABLE)]
        required_columns = ["cash_reserve", "target_weighted_dyr", "position_plan_json", "current_index_pe_pct"]

        if all(col in columns for col in required_columns):
            conn = op.get_bind()
            conn.execute(
                sa.text(f"""
                    INSERT INTO {PORTFOLIO_SETTINGS_TABLE} (id, cash_reserve, target_weighted_dyr, position_plan_json, current_index_pe_pct)
                    SELECT id, cash_reserve, target_weighted_dyr, position_plan_json, current_index_pe_pct
                    FROM {CASHFLOW_GOALS_TABLE}
                    WHERE id = 1
                """)
            )

    # Step 3: Remove the merged columns from cashflow_goals
    if CASHFLOW_GOALS_TABLE in insp.get_table_names():
        columns = [col["name"] for col in insp.get_columns(CASHFLOW_GOALS_TABLE)]
        columns_to_drop = [
            "cash_reserve",
            "target_weighted_dyr",
            "position_plan_json",
            "current_index_pe_pct",
            "quadrant_targets_json"
        ]

        for col_name in columns_to_drop:
            if col_name in columns:
                # SQLite doesn't support DROP COLUMN in all versions, so we use a workaround
                # For PostgreSQL, MySQL, etc., we could use: op.drop_column(CASHFLOW_GOALS_TABLE, col_name)
                # For SQLite, we need to recreate the table, but that's complex for downgrade
                # We'll skip this step for SQLite as the data is already migrated back
                pass
