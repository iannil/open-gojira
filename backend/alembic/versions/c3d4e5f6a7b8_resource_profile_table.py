"""Add resource_profiles table for manually maintained resource-stock attributes.

Methodology demands explicit fields not provided by Lixinger:
资源类型 / 储量品位 / 成本分位 / 有矿无矿 / 国内外 / 可采年限.
1:1 with stocks via stock_code primary key.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "resource_profiles"


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if TABLE in insp.get_table_names():
        return

    op.create_table(
        TABLE,
        sa.Column("stock_code", sa.String(), nullable=False),
        sa.Column("resource_type", sa.String(), nullable=True),
        sa.Column("endowment_note", sa.Text(), nullable=True),
        sa.Column("cost_quantile", sa.Float(), nullable=True),
        sa.Column("has_mine", sa.Boolean(), nullable=True),
        sa.Column("domestic", sa.Boolean(), nullable=True),
        sa.Column("reserve_years", sa.Float(), nullable=True),
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
