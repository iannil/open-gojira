"""G4 resource flags: Stock.has_mine + Stock.domestic_leader

Revision ID: t9_1_g4_resource_flags
Revises: t8_1_g1_cycle_gate
Create Date: 2026-06-14

G4 (invest3 §12 "没矿的有色股他会很警惕" + "国内优先"):
- stocks.has_mine: bool | null — True = 自有矿产资源
- stocks.domestic_leader: bool | null — True = 国内资源板块领先
- resource_hard_asset 策略加 2 条 == 规则,null = inconclusive → 剔除
- seeder 预填 ~7 个公开案例 (BFNY/NSLY/BTGF/CHGF/紫金/山东黄金/中金黄金)

设计: grill-me 2026-06-14 (Q11=B 核心 2 维 + Seeder 预填).
"""
revision = "t9_1_g4_resource_flags"
down_revision = "t8_1_g1_cycle_gate"
branch_labels = None
depends_on = None

import sqlalchemy as sa  # noqa: E402
from alembic import op  # noqa: E402


def upgrade():
    with op.batch_alter_table("stocks", schema=None) as batch_op:
        batch_op.add_column(sa.Column("has_mine", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("domestic_leader", sa.Boolean(), nullable=True))
        batch_op.create_index("ix_stocks_has_mine", ["has_mine"], unique=False)
        batch_op.create_index(
            "ix_stocks_domestic_leader", ["domestic_leader"], unique=False
        )


def downgrade():
    with op.batch_alter_table("stocks", schema=None) as batch_op:
        batch_op.drop_index("ix_stocks_domestic_leader")
        batch_op.drop_index("ix_stocks_has_mine")
        batch_op.drop_column("domestic_leader")
        batch_op.drop_column("has_mine")
