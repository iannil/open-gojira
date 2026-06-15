"""Serenity research module: 7 new tables

Revision ID: s1_serenity_research_module
Revises: t11_1_b2_resource_v2
Create Date: 2026-06-15

Serenity-skill integration (spec: docs/reference/specs/2026-06-14-serenity-skill-integration.md).
7 new tables:
- research_themes (research subject, e.g. "AI 半导体"; distinct from Theme macro lines)
- research_runs (single execution; Q8 cost tracking)
- value_chain_layers (8 standard layers per run)
- scarce_layers (3-5 ranked bottlenecks)
- research_company_universe (≥20 candidates per run)
- research_evidence (≥25 sources per run, 4-grade ladder)
- research_company_ranking (Top 3-7 priority picks)

Q14 index: stock_code columns on universe / evidence / ranking are indexed
to accelerate StockDetail reverse-link lookups.
"""
revision = "s1_serenity_research_module"
down_revision = "t11_1_b2_resource_v2"
branch_labels = None
depends_on = None

import sqlalchemy as sa  # noqa: E402
from alembic import op  # noqa: E402


def upgrade():
    # 1) research_themes
    op.create_table(
        "research_themes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("market", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("auto_refresh_freq", sa.String(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_run_status", sa.String(), nullable=True),
        sa.Column("last_run_error", sa.Text(), nullable=True),
        sa.Column("parent_theme_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["parent_theme_id"], ["themes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_research_themes_status", "research_themes", ["status"])
    op.create_index("ix_research_themes_last_run_at", "research_themes", ["last_run_at"])

    # 2) research_runs
    op.create_table(
        "research_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("research_theme_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("scope_market", sa.String(), nullable=False),
        sa.Column("scope_time_window", sa.String(), nullable=False),
        sa.Column("triggered_by", sa.String(), nullable=False),
        sa.Column("llm_provider", sa.String(), nullable=False),
        sa.Column("llm_token_input", sa.Integer(), nullable=False),
        sa.Column("llm_token_output", sa.Integer(), nullable=False),
        sa.Column("llm_search_count", sa.Integer(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("system_change_md", sa.Text(), nullable=True),
        sa.Column("failure_conditions_md", sa.Text(), nullable=True),
        sa.Column("next_steps_md", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["research_theme_id"], ["research_themes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_research_runs_research_theme_id", "research_runs", ["research_theme_id"])

    # 3) value_chain_layers
    op.create_table(
        "value_chain_layers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("research_run_id", sa.Integer(), nullable=False),
        sa.Column("layer_index", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["research_run_id"], ["research_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_value_chain_layers_research_run_id",
        "value_chain_layers",
        ["research_run_id"],
    )

    # 4) scarce_layers
    op.create_table(
        "scarce_layers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("research_run_id", sa.Integer(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("layer_ref_id", sa.Integer(), nullable=False),
        sa.Column("scarcity_reason_md", sa.Text(), nullable=False),
        sa.Column("expansion_difficulty", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["research_run_id"], ["research_runs.id"]),
        sa.ForeignKeyConstraint(["layer_ref_id"], ["value_chain_layers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scarce_layers_research_run_id", "scarce_layers", ["research_run_id"])

    # 5) research_company_universe (Q14: stock_code index for reverse-link)
    op.create_table(
        "research_company_universe",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("research_run_id", sa.Integer(), nullable=False),
        sa.Column("stock_code", sa.String(), nullable=False),
        sa.Column("classification", sa.String(), nullable=False),
        sa.Column("layer_ref_id", sa.Integer(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["research_run_id"], ["research_runs.id"]),
        sa.ForeignKeyConstraint(["layer_ref_id"], ["value_chain_layers.id"]),
        sa.ForeignKeyConstraint(["stock_code"], ["stocks.code"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_research_company_universe_research_run_id",
        "research_company_universe",
        ["research_run_id"],
    )
    op.create_index(
        "ix_research_company_universe_stock_code",
        "research_company_universe",
        ["stock_code"],
    )

    # 6) research_evidence (Q14: stock_code index for reverse-link)
    op.create_table(
        "research_evidence",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("research_run_id", sa.Integer(), nullable=False),
        sa.Column("stock_code", sa.String(), nullable=True),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_title", sa.String(), nullable=False),
        sa.Column("published_at", sa.Date(), nullable=True),
        sa.Column("grade", sa.String(), nullable=False),
        sa.Column("summary_md", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["research_run_id"], ["research_runs.id"]),
        sa.ForeignKeyConstraint(["stock_code"], ["stocks.code"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_research_evidence_research_run_id", "research_evidence", ["research_run_id"]
    )
    op.create_index("ix_research_evidence_stock_code", "research_evidence", ["stock_code"])
    op.create_index("ix_research_evidence_grade", "research_evidence", ["grade"])

    # 7) research_company_ranking (Q14: stock_code index for reverse-link)
    op.create_table(
        "research_company_ranking",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("research_run_id", sa.Integer(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("stock_code", sa.String(), nullable=False),
        sa.Column("constrains_what", sa.String(), nullable=False),
        sa.Column("chain_position", sa.String(), nullable=False),
        sa.Column("rank_reason_md", sa.Text(), nullable=False),
        sa.Column("evidence_summary_md", sa.Text(), nullable=False),
        sa.Column("main_risk_md", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["research_run_id"], ["research_runs.id"]),
        sa.ForeignKeyConstraint(["stock_code"], ["stocks.code"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_research_company_ranking_research_run_id",
        "research_company_ranking",
        ["research_run_id"],
    )
    op.create_index(
        "ix_research_company_ranking_stock_code",
        "research_company_ranking",
        ["stock_code"],
    )


def downgrade():
    op.drop_index("ix_research_company_ranking_stock_code", table_name="research_company_ranking")
    op.drop_index("ix_research_company_ranking_research_run_id", table_name="research_company_ranking")
    op.drop_table("research_company_ranking")

    op.drop_index("ix_research_evidence_grade", table_name="research_evidence")
    op.drop_index("ix_research_evidence_stock_code", table_name="research_evidence")
    op.drop_index("ix_research_evidence_research_run_id", table_name="research_evidence")
    op.drop_table("research_evidence")

    op.drop_index("ix_research_company_universe_stock_code", table_name="research_company_universe")
    op.drop_index("ix_research_company_universe_research_run_id", table_name="research_company_universe")
    op.drop_table("research_company_universe")

    op.drop_index("ix_scarce_layers_research_run_id", table_name="scarce_layers")
    op.drop_table("scarce_layers")

    op.drop_index("ix_value_chain_layers_research_run_id", table_name="value_chain_layers")
    op.drop_table("value_chain_layers")

    op.drop_index("ix_research_runs_research_theme_id", table_name="research_runs")
    op.drop_table("research_runs")

    op.drop_index("ix_research_themes_last_run_at", table_name="research_themes")
    op.drop_index("ix_research_themes_status", table_name="research_themes")
    op.drop_table("research_themes")
