"""Add analysis_snapshots, candidate_pools, action_logs.

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-06-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "g7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, name: str) -> bool:
    return name in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "analysis_snapshots"):
        op.create_table(
            "analysis_snapshots",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("stock_code", sa.String, sa.ForeignKey("stocks.code"), nullable=False),
            sa.Column("snapshot_date", sa.Date, nullable=False),
            sa.Column("industry", sa.String, nullable=True),
            sa.Column("security_theme", sa.String, nullable=True),
            sa.Column("qiu_score", sa.Integer, server_default="0"),
            sa.Column("score_total", sa.Integer, server_default="0"),
            sa.Column("score_max", sa.Integer, server_default="0"),
            sa.Column("score_pct", sa.Float, server_default="0"),
            sa.Column("pe_ttm", sa.Float, nullable=True),
            sa.Column("pb", sa.Float, nullable=True),
            sa.Column("pe_pct_10y", sa.Float, nullable=True),
            sa.Column("pb_pct_10y", sa.Float, nullable=True),
            sa.Column("dividend_yield", sa.Float, nullable=True),
            sa.Column("cash_flow_quality", sa.Float, nullable=True),
            sa.Column("valuation_band", sa.String, server_default="yellow"),
            sa.Column("verdict", sa.String, server_default="AVOID"),
            sa.Column("missing_data", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
            sa.UniqueConstraint("stock_code", "snapshot_date", name="uq_snapshot_code_date"),
        )
        op.create_index(
            "ix_analysis_snapshots_stock_code", "analysis_snapshots", ["stock_code"]
        )
        op.create_index(
            "ix_analysis_snapshots_snapshot_date", "analysis_snapshots", ["snapshot_date"]
        )

    if not _has_table(bind, "candidate_pools"):
        op.create_table(
            "candidate_pools",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("pool_date", sa.Date, nullable=False),
            sa.Column("kind", sa.String, server_default="daily"),
            sa.Column("items", sa.Text, nullable=False),
            sa.Column("summary", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
            sa.UniqueConstraint("pool_date", "kind", name="uq_candidate_pool_date_kind"),
        )
        op.create_index("ix_candidate_pools_pool_date", "candidate_pools", ["pool_date"])

    if not _has_table(bind, "action_logs"):
        op.create_table(
            "action_logs",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("event_type", sa.String, nullable=False),
            sa.Column("stock_code", sa.String, nullable=True),
            sa.Column("summary", sa.String, nullable=False),
            sa.Column("payload", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        )
        op.create_index("ix_action_logs_event_type", "action_logs", ["event_type"])
        op.create_index("ix_action_logs_stock_code", "action_logs", ["stock_code"])
        op.create_index("ix_action_logs_created_at", "action_logs", ["created_at"])


def downgrade() -> None:
    pass
