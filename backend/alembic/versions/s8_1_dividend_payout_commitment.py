"""Batch 4 (2026-06-17 invest-alignment audit): dividend_payout_commitment_pct field

Revision ID: s8_1_dividend_payout_commitment
Revises: s7_1_audit_opinion_field
Create Date: 2026-06-17

invest3 §八第2节 "如何筛选愿意与股东分享成果的'纯粹赚钱机器'" — 关注公司明示的
forward 分红承诺 (如 BTGF 芭田股份承诺 60% 分红比率).

FinancialStatement.dividend_payout_ratio 是 actual per-period (历史已实现),
与 commitment (forward 承诺) 不同概念. Lixinger 不提供承诺数据,需用户手动
从年报 "未来分红规划" 章节录入.

新字段 Stock.dividend_payout_commitment_pct: Float | None
- nullable: True (大多数股票未公开承诺)
- 单位: 0.0 ~ 1.0 (e.g., 0.60 = 60%)
- 数据源: manual (用户读年报录入)

策略接入:
- 新增 dividend_commitment_leader 策略 (commitment ≥ 0.6)
- core_value plan 可选加 condition

Plan 接入: core_value plan strategy_composition 可附加此 condition 作为可选 filter.
"""
revision = "s8_1_dividend_payout_commitment"
down_revision = "s7_1_audit_opinion_field"
branch_labels = None
depends_on = None

import sqlalchemy as sa  # noqa: E402
from alembic import op  # noqa: E402


def upgrade():
    with op.batch_alter_table("stocks") as batch_op:
        batch_op.add_column(
            sa.Column("dividend_payout_commitment_pct", sa.Float(), nullable=True)
        )


def downgrade():
    with op.batch_alter_table("stocks") as batch_op:
        batch_op.drop_column("dividend_payout_commitment_pct")
