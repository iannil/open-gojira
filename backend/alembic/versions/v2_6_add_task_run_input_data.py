"""v2 (2026-06-27): Add task_runs.input_data column

Revision ID: v2_6_add_task_run_input_data
Revises: v2_5_add_tasks_and_task_runs
Create Date: 2026-06-27

Adds an input_data TEXT column to task_runs for storing per-invocation
parameters (e.g., stock_code for ad-hoc deep research triggers).
"""
from alembic import op
import sqlalchemy as sa


revision = "v2_6_add_task_run_input_data"
down_revision = "v2_5_add_tasks_and_task_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {c["name"] for c in inspector.get_columns("task_runs")}
    if "input_data" not in existing:
        op.add_column(
            "task_runs",
            sa.Column(
                "input_data", sa.Text, nullable=True,
                comment="JSON serialized input parameters for this run",
            ),
        )


def downgrade() -> None:
    op.drop_column("task_runs", "input_data")
