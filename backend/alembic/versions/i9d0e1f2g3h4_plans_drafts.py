"""Autopilot Step 2: plans, plan_exec_history, drafts.

Revision ID: i9d0e1f2g3h4
Revises: h8c9d0e1f2g3
Create Date: 2026-06-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "i9d0e1f2g3h4"
down_revision: Union[str, Sequence[str], None] = "h8c9d0e1f2g3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, name: str) -> bool:
    return name in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "plans"):
        op.create_table(
            "plans",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("code", sa.String, sa.ForeignKey("stocks.code"), nullable=False),
            sa.Column("version", sa.Integer, nullable=False, server_default="1"),
            sa.Column("status", sa.String, nullable=False, server_default="armed"),
            sa.Column("thesis", sa.Text, nullable=False, server_default=""),
            sa.Column("effective_from", sa.Date, nullable=False),
            sa.Column("effective_until", sa.Date, nullable=False),
            sa.Column("spec_json", sa.Text, nullable=False),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime, nullable=True),
            sa.UniqueConstraint("code", "version", name="uq_plans_code_version"),
        )
        op.create_index("ix_plans_code", "plans", ["code"])
        op.create_index("ix_plans_status", "plans", ["status"])

    if not _has_table(bind, "plan_exec_history"):
        op.create_table(
            "plan_exec_history",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("plan_id", sa.Integer, sa.ForeignKey("plans.id"), nullable=False),
            sa.Column("plan_version", sa.Integer, nullable=False),
            sa.Column("step_kind", sa.String, nullable=False),
            sa.Column("step_index", sa.Integer, nullable=False),
            sa.Column("triggered_at", sa.DateTime, server_default=sa.func.now()),
            sa.Column("executed_at", sa.DateTime, nullable=True),
            sa.Column("fill_price", sa.Float, nullable=True),
            sa.Column("fill_quantity", sa.Integer, nullable=True),
        )
        op.create_index(
            "ix_plan_exec_history_plan_id", "plan_exec_history", ["plan_id"]
        )

    if not _has_table(bind, "drafts"):
        op.create_table(
            "drafts",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("plan_id", sa.Integer, sa.ForeignKey("plans.id"), nullable=False),
            sa.Column("plan_version", sa.Integer, nullable=False),
            sa.Column("code", sa.String, sa.ForeignKey("stocks.code"), nullable=False),
            sa.Column("side", sa.String, nullable=False),
            sa.Column("status", sa.String, nullable=False, server_default="pending"),
            sa.Column("step_kind", sa.String, nullable=False),
            sa.Column("step_index", sa.Integer, nullable=False),
            sa.Column("add_pct", sa.Float, nullable=True),
            sa.Column("reduce_pct_of_position", sa.Float, nullable=True),
            sa.Column("reason", sa.Text, nullable=False),
            sa.Column(
                "exec_history_id",
                sa.Integer,
                sa.ForeignKey("plan_exec_history.id"),
                nullable=True,
            ),
            sa.Column("triggered_at", sa.DateTime, server_default=sa.func.now()),
            sa.Column("executed_at", sa.DateTime, nullable=True),
        )
        op.create_index("ix_drafts_plan_id", "drafts", ["plan_id"])
        op.create_index("ix_drafts_code", "drafts", ["code"])
        op.create_index("ix_drafts_status", "drafts", ["status"])
        op.create_index("ix_drafts_triggered_at", "drafts", ["triggered_at"])


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "drafts"):
        op.drop_table("drafts")
    if _has_table(bind, "plan_exec_history"):
        op.drop_table("plan_exec_history")
    if _has_table(bind, "plans"):
        op.drop_table("plans")
