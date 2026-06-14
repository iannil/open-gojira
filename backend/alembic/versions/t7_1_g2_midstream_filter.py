"""G2 midstream filter: BusinessPattern.is_midstream + Stock.is_cost_leader + Plan.disable_midstream_filter

Revision ID: t7_1_g2_midstream_filter
Revises: t6_1_business_patterns
Create Date: 2026-06-14

G2 (invest3 §13 "中游企业一般不要投资，除非它是成本最低的那个"):
- business_patterns.is_midstream: bool (默认 false;煤化工/电解铝=true)
- stocks.is_cost_leader: bool | null (默认 null=inconclusive → plan_runner 剔除)
- plans.disable_midstream_filter: bool (默认 false=启用过滤;plan 级逃生口)

Seeder 在 migration 后 upsert:
- 17 个 builtin patterns 标 is_midstream (2 true / 15 false)
- BUILTIN_COST_LEADERS 预填 (BFNY/NSLY)

设计: grill-me 2026-06-14 (Q5=A Pattern 级 / Q6=B Seeder 预填 / Q7=B plan_runner 过滤).
"""
revision = "t7_1_g2_midstream_filter"
down_revision = "t6_1_business_patterns"
branch_labels = None
depends_on = None

import sqlalchemy as sa  # noqa: E402
from alembic import op  # noqa: E402


def upgrade():
    # BusinessPattern.is_midstream (default false)
    with op.batch_alter_table("business_patterns", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_midstream",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )

    # Stock.is_cost_leader (nullable bool)
    with op.batch_alter_table("stocks", schema=None) as batch_op:
        batch_op.add_column(sa.Column("is_cost_leader", sa.Boolean(), nullable=True))
        batch_op.create_index(
            "ix_stocks_is_cost_leader", ["is_cost_leader"], unique=False
        )

    # Plan.disable_midstream_filter (default false)
    with op.batch_alter_table("plans", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "disable_midstream_filter",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )


def downgrade():
    with op.batch_alter_table("plans", schema=None) as batch_op:
        batch_op.drop_column("disable_midstream_filter")

    with op.batch_alter_table("stocks", schema=None) as batch_op:
        batch_op.drop_index("ix_stocks_is_cost_leader")
        batch_op.drop_column("is_cost_leader")

    with op.batch_alter_table("business_patterns", schema=None) as batch_op:
        batch_op.drop_column("is_midstream")
