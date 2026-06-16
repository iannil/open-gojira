"""research_claims table (Phase 2 #9 / Q19, 2026-06-16)

Revision ID: s4_research_claims
Revises: s3_research_search_results
Create Date: 2026-06-16

Phase 2 #9 implementation: structured failure_conditions / next_steps.

LLM previously output `failure_conditions: list[str]`. Now outputs
`failure_conditions: list[{subject, predicate, signal, outcome,
stock_codes, layer_index}]` (same for next_steps). Each list item is
persisted as one row in research_claims.

`ResearchRun.failure_conditions_md` and `next_steps_md` are kept and
derived from the structured claims for backward compatibility (UI
fallback for legacy runs without structured data).
"""
revision = "s4_research_claims"
down_revision = "s3_research_search_results"
branch_labels = None
depends_on = None

import sqlalchemy as sa  # noqa: E402
from alembic import op  # noqa: E402


def upgrade():
    op.create_table(
        "research_claims",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("research_run_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("predicate", sa.Text(), nullable=False),
        sa.Column("signal", sa.Text(), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("stock_codes_json", sa.Text(), nullable=True),
        sa.Column("layer_index", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["research_run_id"], ["research_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_research_claims_research_run_id",
        "research_claims",
        ["research_run_id"],
    )
    op.create_index(
        "ix_research_claims_type",
        "research_claims",
        ["type"],
    )


def downgrade():
    op.drop_index("ix_research_claims_type", table_name="research_claims")
    op.drop_index(
        "ix_research_claims_research_run_id", table_name="research_claims"
    )
    op.drop_table("research_claims")
