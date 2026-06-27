"""v2 (2026-06-27): Add task_run_logs table

Revision ID: v2_7_add_task_run_logs
Revises: v2_6_add_task_run_input_data
Create Date: 2026-06-27

Adds a task_run_logs table for granular step-by-step execution logging,
enabling the frontend to display detailed progress and execution logs.
"""
from alembic import op
import sqlalchemy as sa


revision = "v2_7_add_task_run_logs"
down_revision = "v2_6_add_task_run_input_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if "task_run_logs" not in existing_tables:
        op.create_table(
            "task_run_logs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("run_id", sa.Integer(), nullable=False),
            sa.Column("timestamp", sa.DateTime(), nullable=False),
            sa.Column("level", sa.String(16), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("progress", sa.Float(), nullable=True),
            sa.ForeignKeyConstraint(
                ["run_id"],
                ["task_runs.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        # Add indexes
        op.create_index(
            "ix_task_run_logs_run_id", "task_run_logs", ["run_id"],
        )
        op.create_index(
            "ix_task_run_logs_timestamp", "task_run_logs", ["timestamp"],
        )


def downgrade() -> None:
    op.drop_table("task_run_logs")
