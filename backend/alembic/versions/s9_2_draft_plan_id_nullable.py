"""Batch 5 (M4 + M2-escape-hatch 2026-06-17): drafts.plan_id nullable + plans.disable_in_circle_filter

Revision ID: s9_2_draft_plan_id_nullable
Revises: s9_1_batch5_tier_rename_and_in_circle
Create Date: 2026-06-17

M4 (invest1 第13章 + invest2 §3 "渣男理论"):
  thesis breach → EventBus → draft_service.create_thesis_breach_sell_draft()
  生成的 SELL draft 没有关联 Plan (论点证伪信号由系统生成,不属于任何预案),
  需要放宽 Draft.plan_id 为 nullable.

  - drafts.plan_id: Integer FK -> plans.id, nullable=True (原 nullable=False)
  - 已有 drafts 行的 plan_id 仍然 NOT NULL (历史数据不受影响)
  - 新 thesis_breach drafts 用 plan_id=NULL + step_kind='thesis_breach' + source='system'

M2 escape hatch (invest3 第四层 + 核心十诫 #9 坚守边界):
  plans.disable_in_circle_filter: BOOLEAN DEFAULT FALSE.
  - False (默认): plan_runner 启用 in_circle 过滤 (Stock.in_circle=False 的剔除)
  - True: 逃生口, 跳过过滤 (用于全市场扫描/学习场景)
"""
revision = "s9_2_draft_plan_id_nullable"
down_revision = "s9_1_batch5_tier_rename_and_in_circle"
branch_labels = None
depends_on = None

import sqlalchemy as sa  # noqa: E402
from alembic import op  # noqa: E402


def upgrade():
    # M4: drafts.plan_id nullable
    with op.batch_alter_table("drafts", schema=None) as batch_op:
        batch_op.alter_column(
            "plan_id",
            existing_type=None,
            nullable=True,
        )

    # M2 escape hatch: plans.disable_in_circle_filter
    with op.batch_alter_table("plans", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("disable_in_circle_filter", sa.Boolean(),
                      nullable=False, server_default=sa.text("0"))
        )


def downgrade():
    with op.batch_alter_table("plans", schema=None) as batch_op:
        batch_op.drop_column("disable_in_circle_filter")

    with op.batch_alter_table("drafts", schema=None) as batch_op:
        op.execute("DELETE FROM drafts WHERE plan_id IS NULL")
        batch_op.alter_column(
            "plan_id",
            existing_type=None,
            nullable=False,
        )
