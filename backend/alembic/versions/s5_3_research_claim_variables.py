"""research_claim_variables table (Phase 2 #9 阶段 B v2, 2026-06-16)

Revision ID: s5_3_claim_variables
Revises: s4_research_claims
Create Date: 2026-06-16

Phase 2 #9 阶段 B v2: stores LLM-proposed thesis monitor variables.

Each row = one ResearchClaim's signal translated to a monitor variable
(e.g. claim signal "净息差<1.3%持续两个季度" → variable_name="净息差",
threshold_critical=1.3, breach_when="lt", source="financial:NIM",
window_periods=2).

State machine: proposed → active (approve) | rejected (reject).
Active vars are checked nightly by thesis_monitor_service.check_claim_variables.

v2 Q4'-C: research_claim_variables is the sole source of truth for claim-derived
monitors. We do NOT copy to Stock.thesis_variables_json.
"""
revision = "s5_3_claim_variables"
down_revision = "s4_research_claims"
branch_labels = None
depends_on = None

import sqlalchemy as sa  # noqa: E402
from alembic import op  # noqa: E402


def upgrade():
    op.create_table(
        "research_claim_variables",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("research_claim_id", sa.Integer(), nullable=False),
        sa.Column("stock_code", sa.String(), nullable=False),
        sa.Column("variable_name", sa.Text(), nullable=False),
        sa.Column("threshold_critical", sa.Float(), nullable=False),
        sa.Column("breach_when", sa.String(), nullable=False),
        sa.Column("unit", sa.String(), nullable=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("window_periods", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="proposed"),
        sa.Column("proposed_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("reviewed_by", sa.String(), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("last_alerted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["research_claim_id"], ["research_claims.id"]),
        sa.ForeignKeyConstraint(["stock_code"], ["stocks.code"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_rcv_research_claim_id",
        "research_claim_variables",
        ["research_claim_id"],
    )
    op.create_index(
        "ix_rcv_stock_code",
        "research_claim_variables",
        ["stock_code"],
    )
    op.create_index(
        "ix_rcv_status",
        "research_claim_variables",
        ["status"],
    )
    # v2 Q-new: business-level dedup uses this composite index
    op.create_index(
        "ix_rcv_stock_var_source",
        "research_claim_variables",
        ["stock_code", "variable_name", "source"],
    )


def downgrade():
    op.drop_index("ix_rcv_stock_var_source", table_name="research_claim_variables")
    op.drop_index("ix_rcv_status", table_name="research_claim_variables")
    op.drop_index("ix_rcv_stock_code", table_name="research_claim_variables")
    op.drop_index("ix_rcv_research_claim_id", table_name="research_claim_variables")
    op.drop_table("research_claim_variables")
