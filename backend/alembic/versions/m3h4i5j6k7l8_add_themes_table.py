"""Add themes table and link plans to themes.

Revision ID: m3h4i5j6k7l8
Revises: l2g3h4i5j6k7
Create Date: 2026-06-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.sql import table, column

revision: str = "m3h4i5j6k7l8"
down_revision: Union[str, Sequence[str], None] = "l2g3h4i5j6k7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

THEMES_TABLE = "themes"
PLANS_TABLE = "plans"


def upgrade() -> None:
    # Step 1: Create themes table
    op.create_table(
        THEMES_TABLE,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("target_weight_pct", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), onupdate=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # Step 2: Add theme_id column to plans table and create foreign key in batch mode (SQLite limitation)
    # Use batch mode for SQLite to handle foreign key creation
    op.add_column(
        PLANS_TABLE,
        sa.Column("theme_id", sa.Integer(), nullable=True)
    )

    # Step 3: Create index on theme_id
    op.create_index("ix_plans_theme_id", PLANS_TABLE, ["theme_id"])

    # Step 4: Seed default themes
    from sqlalchemy.sql import select, insert

    themes_table = table(
        THEMES_TABLE,
        column("id", sa.Integer),
        column("name", sa.Text),
        column("description", sa.Text),
        column("target_weight_pct", sa.Float),
    )

    conn = op.get_bind()

    # Check if themes already exist
    result = conn.execute(select(themes_table.c.id))
    if result.fetchone() is None:
        conn.execute(
            insert(themes_table),
            [
                {
                    "id": 1,
                    "name": "能源安全",
                    "description": "能源安全主线 - 包括传统能源和新能源",
                    "target_weight_pct": 25.0,
                },
                {
                    "id": 2,
                    "name": "资源安全",
                    "description": "资源安全主线 - 包括矿产资源、水资源等",
                    "target_weight_pct": 25.0,
                },
                {
                    "id": 3,
                    "name": "金融安全",
                    "description": "金融安全主线 - 包括银行、保险、券商等",
                    "target_weight_pct": 25.0,
                },
                {
                    "id": 4,
                    "name": "粮食安全",
                    "description": "粮食安全主线 - 包括农业、食品、农资等",
                    "target_weight_pct": 25.0,
                },
            ],
        )


def downgrade() -> None:
    # Step 1: Drop index on theme_id
    op.drop_index("ix_plans_theme_id", table_name=PLANS_TABLE)

    # Step 2: Drop theme_id column from plans table
    op.drop_column(PLANS_TABLE, "theme_id")

    # Step 3: Drop themes table
    op.drop_table(THEMES_TABLE)
