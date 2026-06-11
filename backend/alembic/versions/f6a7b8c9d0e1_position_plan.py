"""Add position_plan_json and current_index_pe_pct to portfolio_settings.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "portfolio_settings"


def _has_column(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, TABLE, "position_plan_json"):
        op.add_column(TABLE, sa.Column("position_plan_json", sa.Text(), nullable=True))
    if not _has_column(bind, TABLE, "current_index_pe_pct"):
        op.add_column(TABLE, sa.Column("current_index_pe_pct", sa.Float(), nullable=True))


def downgrade() -> None:
    pass
