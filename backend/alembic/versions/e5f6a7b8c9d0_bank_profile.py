"""Add bank_profiles table for region/NPL/CAR manual annotations.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "bank_profiles"


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if TABLE in insp.get_table_names():
        return
    op.create_table(
        TABLE,
        sa.Column("stock_code", sa.String(), nullable=False),
        sa.Column("region", sa.String(), nullable=True),
        sa.Column("region_grade", sa.String(), nullable=True),
        sa.Column("population_inflow", sa.Boolean(), nullable=True),
        sa.Column("npl_ratio", sa.Float(), nullable=True),
        sa.Column("capital_adequacy", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["stock_code"], ["stocks.code"]),
        sa.PrimaryKeyConstraint("stock_code"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if TABLE not in insp.get_table_names():
        return
    op.drop_table(TABLE)
