"""D3 (2026-06-17 invest-alignment audit): 财报红旗 schema 扩展

Revision ID: s6_1_red_flag_fields
Revises: s5_3_claim_variables
Create Date: 2026-06-17

invest1 §三 + invest2 §10 财报避坑。新增 4 个 FinancialStatement 字段用于
红旗检测 (商誉雷/伪造销售/存货积压/非经常损益依赖):
  - accounts_receivable (应收账款, Lixinger bs.ar.t)
  - inventory (存货, Lixinger bs.inv.t)
  - inventory_turnover_ratio (存货周转率, Lixinger m.i_tor.t)
  - non_recurring_profit_ratio (扣非净利率, Lixinger ps.np_wd_s_r.t)

注: Lixinger 字段键是基于通用命名推断,实际 API 兼容性需要 spike 验证。
若键不存在,Lixinger 返回该字段为 null → 该红旗检测自动跳过 (graceful)。

不新增 audit_opinion 字段: Lixinger 标准 API 不提供审计意见,跳过。
"""
revision = "s6_1_red_flag_fields"
down_revision = "s5_3_claim_variables"
branch_labels = None
depends_on = None

import sqlalchemy as sa  # noqa: E402
from alembic import op  # noqa: E402


def upgrade():
    with op.batch_alter_table("financial_statements") as batch_op:
        batch_op.add_column(sa.Column("accounts_receivable", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("inventory", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("inventory_turnover_ratio", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("non_recurring_profit_ratio", sa.Float(), nullable=True))


def downgrade():
    with op.batch_alter_table("financial_statements") as batch_op:
        batch_op.drop_column("non_recurring_profit_ratio")
        batch_op.drop_column("inventory_turnover_ratio")
        batch_op.drop_column("inventory")
        batch_op.drop_column("accounts_receivable")
