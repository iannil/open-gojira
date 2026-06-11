"""Autopilot Step 1 foundation: cashflow_goals, audit_logs, stocks.quadrant.

Revision ID: h8c9d0e1f2g3
Revises: g7b8c9d0e1f2
Create Date: 2026-06-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "h8c9d0e1f2g3"
down_revision: Union[str, Sequence[str], None] = "g7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, name: str) -> bool:
    return name in sa.inspect(bind).get_table_names()


def _has_column(bind, table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "cashflow_goals"):
        op.create_table(
            "cashflow_goals",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=False),
            sa.Column("annual_expense", sa.Float, nullable=False, server_default="0"),
            sa.Column("goal_multiple", sa.Float, nullable=False, server_default="15"),
            sa.Column("currency", sa.Text, nullable=False, server_default="CNY"),
            sa.Column("notes", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime, nullable=True),
        )

    if not _has_table(bind, "audit_logs"):
        op.create_table(
            "audit_logs",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("entity_type", sa.String, nullable=False),
            sa.Column("entity_id", sa.String, nullable=True),
            sa.Column("event", sa.String, nullable=False),
            sa.Column("actor", sa.String, nullable=False, server_default="system"),
            sa.Column("stock_code", sa.String, nullable=True),
            sa.Column("summary", sa.String, nullable=False),
            sa.Column("payload", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        )
        op.create_index("ix_audit_logs_entity_type", "audit_logs", ["entity_type"])
        op.create_index("ix_audit_logs_entity_id", "audit_logs", ["entity_id"])
        op.create_index("ix_audit_logs_event", "audit_logs", ["event"])
        op.create_index("ix_audit_logs_stock_code", "audit_logs", ["stock_code"])
        op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    if _has_table(bind, "stocks") and not _has_column(bind, "stocks", "quadrant"):
        with op.batch_alter_table("stocks") as batch:
            batch.add_column(sa.Column("quadrant", sa.String, nullable=True))


def downgrade() -> None:
    bind = op.get_bind()

    if _has_table(bind, "stocks") and _has_column(bind, "stocks", "quadrant"):
        with op.batch_alter_table("stocks") as batch:
            batch.drop_column("quadrant")

    if _has_table(bind, "audit_logs"):
        op.drop_table("audit_logs")
    if _has_table(bind, "cashflow_goals"):
        op.drop_table("cashflow_goals")
