"""add business_patterns table + stocks.business_pattern_id

Revision ID: t6_1_business_patterns
Revises: s5_2_notifications
Create Date: 2026-06-14

T6.1: 产业研究模块 (BusinessPattern). 见 docs/progress 与 invest1/2/3 方法论.

- 新建 business_patterns 表 — 生意模式 (煤化工/电解铝/药店零售/...) 的 context 模板
- stocks 表加 business_pattern_id FK + business_pattern_inferred_at timestamp
- is_builtin=True 的行由 builtin_seeder 在启动时 upsert

设计参考: 12 项决策对话(2026-06-14),后续 service/router/frontend 在 T6.2-T6.9 推进.
"""
revision = "t6_1_business_patterns"
down_revision = "s5_2_notifications"
branch_labels = None
depends_on = None

import sqlalchemy as sa  # noqa: E402
from alembic import op  # noqa: E402


def upgrade():
    op.create_table(
        "business_patterns",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("theme_id", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("first_principle_variable", sa.Text(), nullable=True),
        sa.Column(
            "power_tier_baseline",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("thesis_variables_json", sa.Text(), nullable=True),
        sa.Column("lixinger_industries_json", sa.Text(), nullable=True),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column(
            "is_builtin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            onupdate=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.ForeignKeyConstraint(["theme_id"], ["themes.id"]),
    )
    op.create_index(
        "ix_business_patterns_theme_id", "business_patterns", ["theme_id"]
    )
    op.create_index(
        "ix_business_patterns_is_builtin", "business_patterns", ["is_builtin"]
    )

    # Stock 表加 business_pattern_id + business_pattern_inferred_at
    op.add_column(
        "stocks",
        sa.Column("business_pattern_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "stocks",
        sa.Column("business_pattern_inferred_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_stocks_business_pattern_id",
        "stocks",
        ["business_pattern_id"],
    )
    op.create_foreign_key(
        "fk_stocks_business_pattern_id",
        "stocks",
        "business_patterns",
        ["business_pattern_id"],
        ["id"],
    )


def downgrade():
    op.drop_constraint(
        "fk_stocks_business_pattern_id", "stocks", type_="foreignkey"
    )
    op.drop_index("ix_stocks_business_pattern_id", table_name="stocks")
    op.drop_column("stocks", "business_pattern_inferred_at")
    op.drop_column("stocks", "business_pattern_id")

    op.drop_index("ix_business_patterns_is_builtin", table_name="business_patterns")
    op.drop_index("ix_business_patterns_theme_id", table_name="business_patterns")
    op.drop_table("business_patterns")
