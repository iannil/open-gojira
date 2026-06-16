"""research_search_results table (serenity Path B 2026-06-16)

Revision ID: s3_research_search_results
Revises: s2_candidate_source_field
Create Date: 2026-06-16

Path B refactor: serenity research uses two-step search → synthesis.
Step 1 collects ~30 queries' real results from `client.web_search.web_search()`
standalone API. Step 2 LLM synthesis must cite URLs from this table.

Without this table, GLM-5.1 hallucinated evidence URLs (curl-confirmed
2026-06-16: cninfo returned size 0, pbc.gov.cn returned 404). serenity spec
requires ≥25 sources via web_search — Phase 1 #9 ship standard was silently
violated.
"""
revision = "s3_research_search_results"
down_revision = "s2_candidate_source_field"
branch_labels = None
depends_on = None

import sqlalchemy as sa  # noqa: E402
from alembic import op  # noqa: E402


def upgrade():
    op.create_table(
        "research_search_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "research_run_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column("search_query", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.Column("media", sa.String(), nullable=True),
        sa.Column("published_at", sa.Date(), nullable=True),
        sa.Column("refer", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["research_run_id"], ["research_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_research_search_results_research_run_id",
        "research_search_results",
        ["research_run_id"],
    )
    op.create_index(
        "ix_research_search_results_search_query",
        "research_search_results",
        ["search_query"],
    )
    op.create_index(
        "ix_research_search_results_url",
        "research_search_results",
        ["url"],
    )


def downgrade():
    op.drop_index(
        "ix_research_search_results_url", table_name="research_search_results"
    )
    op.drop_index(
        "ix_research_search_results_search_query",
        table_name="research_search_results",
    )
    op.drop_index(
        "ix_research_search_results_research_run_id",
        table_name="research_search_results",
    )
    op.drop_table("research_search_results")
