"""v2 (2026-06-26): Add tasks + task_runs for unified task scheduling

Revision ID: v2_5_add_tasks_and_task_runs
Revises: v2_4_drop_holdings_table
Create Date: 2026-06-26

Adds the core tables for the Task Scheduling Redesign (Phase 1):

- tasks: unified task definitions (replaces scheduler_jobs eventually)
- task_runs: execution instances (replaces job_executions eventually)

Seed: existing scheduler_jobs are copied into tasks table on migration.

This is ADD-ONLY — existing scheduler_jobs / job_executions remain untouched
until Phase 3 cleanup.
"""
from alembic import op
import sqlalchemy as sa


revision = "v2_5_add_tasks_and_task_runs"
down_revision = "v2_4_drop_holdings_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # ── tasks ────────────────────────────────────────────────────────────────
    if "tasks" not in existing_tables:
        op.create_table(
            "tasks",
            sa.Column("task_id", sa.String(128), primary_key=True),
            sa.Column("type", sa.String(32), nullable=False, server_default="job"),
            sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
            sa.Column("trigger_type", sa.String(16), nullable=False, server_default="cron"),
            sa.Column("cron_expr", sa.String(64), nullable=True),
            sa.Column("event_source", sa.String(64), nullable=True),
            sa.Column("depends_on", sa.Text, nullable=True,
                      comment="JSON array of task_id's"),
            sa.Column("retry_config", sa.Text, nullable=True,
                      comment='JSON: {"max_retries":3,"backoff":"exponential"}'),
            sa.Column("timeout_seconds", sa.Integer, nullable=True, server_default="300"),
            sa.Column("mutex_enabled", sa.Boolean, nullable=False, server_default="1"),
            sa.Column("enabled", sa.Boolean, nullable=False, server_default="1"),
            sa.Column("tags", sa.Text, nullable=True,
                      comment="JSON array of tag strings"),
            sa.Column("description", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime, nullable=False,
                      server_default=sa.func.datetime("now")),
            sa.Column("updated_at", sa.DateTime, nullable=False,
                      server_default=sa.func.datetime("now")),
            sqlite_autoincrement=False,
        )

    # ── task_runs ────────────────────────────────────────────────────────────
    if "task_runs" not in existing_tables:
        op.create_table(
            "task_runs",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("task_id", sa.String(128), nullable=False),
            sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
            sa.Column("progress", sa.Float, nullable=False, server_default="0.0"),
            sa.Column("progress_message", sa.Text, nullable=True),
            sa.Column("started_at", sa.DateTime, nullable=True),
            sa.Column("finished_at", sa.DateTime, nullable=True),
            sa.Column("duration_ms", sa.Integer, nullable=True),
            sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
            sa.Column("max_retries", sa.Integer, nullable=False, server_default="0"),
            sa.Column("last_error", sa.Text, nullable=True),
            sa.Column("result_summary", sa.Text, nullable=True),
            sa.Column("worker_id", sa.String(64), nullable=True),
            sa.Column("triggered_by", sa.String(32), nullable=False, server_default="cron"),
            sa.Column("trace_id", sa.String(64), nullable=True),
            sa.Column("created_at", sa.DateTime, nullable=False, index=True,
                      server_default=sa.func.datetime("now")),
        )

    # ── indexes ──────────────────────────────────────────────────────────────
    existing_indexes = {ix["name"] for ix in inspector.get_indexes("task_runs")} if "task_runs" in existing_tables else set()

    if "idx_task_runs_task_id" not in existing_indexes:
        op.create_index("idx_task_runs_task_id", "task_runs", ["task_id"])
    if "idx_task_runs_status" not in existing_indexes:
        op.create_index("idx_task_runs_status", "task_runs", ["status"])

    # ── seed from existing scheduler_jobs ────────────────────────────────────
    if "scheduler_jobs" in inspector.get_table_names() and "tasks" not in existing_tables:
        conn = op.get_bind()
        rows = conn.execute(
            sa.text("SELECT job_id, cron_expr, enabled, description FROM scheduler_jobs")
        ).fetchall()
        for row in rows:
            retry_config = '{"max_retries":3,"backoff":"exponential","max_delay_seconds":300}'
            description = row[3] if row[3] else ""
            conn.execute(
                sa.text("""
                    INSERT INTO tasks (task_id, type, status, trigger_type, cron_expr,
                                       retry_config, timeout_seconds, mutex_enabled,
                                       enabled, description, tags)
                    VALUES (:task_id, 'job', 'active', 'cron', :cron_expr,
                            :retry_config, 600, 1,
                            :enabled, :description, '["seed"]')
                """),
                {
                    "task_id": row[0],
                    "cron_expr": row[1],
                    "enabled": 1 if row[2] else 0,
                    "description": description,
                    "retry_config": retry_config,
                },
            )


def downgrade() -> None:
    op.drop_table("task_runs")
    op.drop_table("tasks")
