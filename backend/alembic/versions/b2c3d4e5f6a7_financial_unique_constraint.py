"""FinancialStatement unique (stock_code, report_date, report_type).

Removes pre-existing duplicate rows (keeping the highest id, which is
the latest write) and adds a UniqueConstraint matching the model so the
upsert in fetch_and_store_financials is durably idempotent.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONSTRAINT_NAME = "uq_financial_stmt_code_date_type"
TABLE = "financial_statements"
COLS = ("stock_code", "report_date", "report_type")


def _constraint_exists(bind, table: str, name: str) -> bool:
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    for c in insp.get_unique_constraints(table):
        if c.get("name") == name:
            return True
    return False


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if TABLE not in insp.get_table_names():
        # Fresh DB: create_all already covers it from the model.
        return

    # Dedup: keep max(id) per (stock_code, report_date, report_type).
    bind.execute(sa.text(
        """
        DELETE FROM financial_statements
        WHERE id NOT IN (
            SELECT MAX(id) FROM financial_statements
            GROUP BY stock_code, report_date, report_type
        )
        """
    ))

    if _constraint_exists(bind, TABLE, CONSTRAINT_NAME):
        return

    with op.batch_alter_table(TABLE) as batch:
        batch.create_unique_constraint(CONSTRAINT_NAME, list(COLS))


def downgrade() -> None:
    bind = op.get_bind()
    if not _constraint_exists(bind, TABLE, CONSTRAINT_NAME):
        return
    with op.batch_alter_table(TABLE) as batch:
        batch.drop_constraint(CONSTRAINT_NAME, type_="unique")
