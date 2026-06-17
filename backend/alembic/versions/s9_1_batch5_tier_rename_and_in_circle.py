"""Batch 5 (2026-06-17 invest-alignment 3rd grill): tier rename + in_circle field

Revision ID: s9_1_batch5_tier_rename_and_in_circle
Revises: s8_1_dividend_payout_commitment
Create Date: 2026-06-17

Batch 5 决策 (3rd grill-me 产出):

Q2 — tier 命名重构 (专业金融名词):
  Stock.tier 字段值 'watch' → 'satellite' (Core-Satellite Model).
  理由: 'watch' 是"自选股"语义, 与"卫星/投机小仓位" invest2 §13 / invest3 玄阶语义
  不匹配. 改用金融行业通用 Core-Satellite 二分法, 与 Batch 4 'core' 字段值配对.
  - 'core' 不变 (核心仓位 ≈ invest3 天阶)
  - 'watch' → 'satellite' (卫星仓位 ≈ invest3 玄阶, 可小仓位玩预期差)
  - 'focus' / None 不变
  注: Batch 4 已 seed 3 元组 tier='watch' (002749/603199 等), 这里 UPDATE 迁移.

M2 — 能力圈边界 (invest3 第四层 + 核心十诫 #9 "坚守边界"):
  新字段 Stock.in_circle: BOOLEAN DEFAULT FALSE.
  - False (默认): 所有 stock 需用户主动 toggle 标记
  - True: 在用户能力圈内, plan_runner filter stage 放行
  - 索引: idx_stocks_in_circle (plan_runner 高频过滤)

  invest1/2/3 三本都反复强调"不懂不做", 但 4 批 audit 完全没碰过能力圈实现.
  Batch 5 补齐: Stock.in_circle + UI toggle (UniversePage / StockDetailPage)
  + plan_runner filter + CandidatesPage filter.
"""
revision = "s9_1_batch5_tier_rename_and_in_circle"
down_revision = "s8_1_dividend_payout_commitment"
branch_labels = None
depends_on = None

import sqlalchemy as sa  # noqa: E402
from alembic import op  # noqa: E402


def upgrade():
    # M2: add in_circle column + index
    with op.batch_alter_table("stocks") as batch_op:
        batch_op.add_column(
            sa.Column("in_circle", sa.Boolean(), nullable=False, server_default=sa.text("0"))
        )
    op.create_index("idx_stocks_in_circle", "stocks", ["in_circle"])

    # Q2: rename tier 'watch' → 'satellite' (data migration)
    op.execute("UPDATE stocks SET tier = 'satellite' WHERE tier = 'watch'")


def downgrade():
    # Q2 revert
    op.execute("UPDATE stocks SET tier = 'watch' WHERE tier = 'satellite'")

    # M2 revert
    op.drop_index("idx_stocks_in_circle", table_name="stocks")
    with op.batch_alter_table("stocks") as batch_op:
        batch_op.drop_column("in_circle")
