"""B2 resource v2: Stock.expansion_outlook + Stock.geo_risk

Revision ID: t11_1_b2_resource_v2
Revises: t10_1_b3_themes_expansion
Create Date: 2026-06-14

B2 (invest3 §12 资源股 7 维剩余 2 维):
- stocks.expansion_outlook: bool | null — True = 明确扩产计划
- stocks.geo_risk: bool | null — True = 地缘税收风险可接受
- resource_hard_asset 策略加 2 条 == True 规则
- null = inconclusive → 剔除 (与 G2/G3/G4 fallback 一致)
"""
revision = "t11_1_b2_resource_v2"
down_revision = "t10_1_b3_themes_expansion"
branch_labels = None
depends_on = None

import sqlalchemy as sa  # noqa: E402
from alembic import op  # noqa: E402


def upgrade():
    with op.batch_alter_table("stocks", schema=None) as batch_op:
        batch_op.add_column(sa.Column("expansion_outlook", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("geo_risk", sa.Boolean(), nullable=True))


def downgrade():
    with op.batch_alter_table("stocks", schema=None) as batch_op:
        batch_op.drop_column("geo_risk")
        batch_op.drop_column("expansion_outlook")
