"""G1 cycle gate: Plan.cycle_buy_max

Revision ID: t8_1_g1_cycle_gate
Revises: t7_1_g2_midstream_filter
Create Date: 2026-06-14

G1 (invest3 §5 "大盘整体高位时回撤会无差别打击"):
- plans.cycle_buy_max: str (默认 'mid'; enum: extreme_low/low/mid/high/extreme_high)
- plan_runner 在 trading rules 评估前检查 cycle gate,rank > max → 阻断 BUY drafts
- cycle 数据缺失 (pe_pct_10y=None) → 整个 plan run 跳过

设计: grill-me 2026-06-14 (Q8=A 仅买入 gate / Q9=A 单字段默认 mid / Q10=C plan-level skip).
"""
revision = "t8_1_g1_cycle_gate"
down_revision = "t7_1_g2_midstream_filter"
branch_labels = None
depends_on = None

import sqlalchemy as sa  # noqa: E402
from alembic import op  # noqa: E402


def upgrade():
    with op.batch_alter_table("plans", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "cycle_buy_max",
                sa.String(),
                nullable=False,
                server_default="mid",
            )
        )


def downgrade():
    with op.batch_alter_table("plans", schema=None) as batch_op:
        batch_op.drop_column("cycle_buy_max")
