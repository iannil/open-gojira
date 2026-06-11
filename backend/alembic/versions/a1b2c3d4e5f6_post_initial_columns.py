"""Post-initial columns: discipline_checks.max_score, stocks.listed_date.

These two columns were added to the models after the initial Alembic
stamp (3d11e6a6f1d2) and were previously bolted on at startup by an
ad-hoc ``_migrate_existing_tables`` helper in app/main.py. This
revision moves them into the proper migration history so that fresh
dev databases and existing ones converge through the same channel.

Revision ID: a1b2c3d4e5f6
Revises: 3d11e6a6f1d2
Create Date: 2026-06-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "3d11e6a6f1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def _has_table(bind, table: str) -> bool:
    return table in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "discipline_checks") and not _has_column(bind, "discipline_checks", "max_score"):
        op.add_column(
            "discipline_checks",
            sa.Column("max_score", sa.Integer(), nullable=True),
        )
    if _has_table(bind, "stocks") and not _has_column(bind, "stocks", "listed_date"):
        op.add_column(
            "stocks",
            sa.Column("listed_date", sa.Date(), nullable=True),
        )


def downgrade() -> None:
    # SQLite drops columns via batch op.
    with op.batch_alter_table("stocks") as batch:
        batch.drop_column("listed_date")
    with op.batch_alter_table("discipline_checks") as batch:
        batch.drop_column("max_score")
