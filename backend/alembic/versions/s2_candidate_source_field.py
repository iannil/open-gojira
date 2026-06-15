"""Candidate.source field + plan_id nullable (serenity integration)

Revision ID: s2_candidate_source_field
Revises: s1_serenity_research_module
Create Date: 2026-06-15

Two schema changes for serenity Phase 2:

1. Add `candidates.source` column to distinguish rule-based candidates
   (plan_runner output) from serenity-research-exported candidates.
   Q3 D decision: serenity LLM-exported Candidates must be tagged distinctly
   from rule-based Candidates to avoid semantic confusion in downstream
   audit/draft_matcher/position_advisor consumers.

2. Make `candidates.plan_id` nullable. Serenity-exported Candidates have no
   user Plan — they come from LLM research. Previously worked around via a
   sentinel Plan (lazy-created with status='archived'); now removed in favor
   of nullable FK. rule_based Candidates still require plan_id (enforced in
   candidate_service business logic, not DB constraint).
"""
revision = "s2_candidate_source_field"
down_revision = "s1_serenity_research_module"
branch_labels = None
depends_on = None

import sqlalchemy as sa  # noqa: E402
from alembic import op  # noqa: E402


def upgrade():
    with op.batch_alter_table("candidates", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "source",
                sa.String(),
                nullable=False,
                server_default="rule_based",
            )
        )
        batch_op.alter_column(
            "plan_id",
            existing_type=sa.Integer(),
            nullable=True,
        )
    op.create_index("ix_candidates_source", "candidates", ["source"])


def downgrade():
    op.drop_index("ix_candidates_source", table_name="candidates")
    with op.batch_alter_table("candidates", schema=None) as batch_op:
        batch_op.alter_column(
            "plan_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.drop_column("source")
