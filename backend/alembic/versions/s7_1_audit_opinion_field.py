"""Batch 3 (2026-06-17 invest-alignment audit spike): audit_opinion field

Revision ID: s7_1_audit_opinion_field
Revises: s6_1_red_flag_fields
Create Date: 2026-06-17

spike (backend/spikes/probe_redflag_metrics.py) 验证 Lixinger fs 端点每行返回
top-level `auditOpinionType` 字段 (4/4 测试股票 = "unqualified_opinion").

原 D3 决策 (s6_1_red_flag_fields.py) 注释"Lixinger 标准 API 不提供审计意见,跳过"
是错误的——auditOpinionType 一直就在返回,只是 financial_service.py 没消费.

本 migration 新增 audit_opinion 字段,补齐 D3 #6 红旗 (非标准审计意见).
"""
revision = "s7_1_audit_opinion_field"
down_revision = "s6_1_red_flag_fields"
branch_labels = None
depends_on = None

import sqlalchemy as sa  # noqa: E402
from alembic import op  # noqa: E402


def upgrade():
    with op.batch_alter_table("financial_statements") as batch_op:
        batch_op.add_column(sa.Column("audit_opinion", sa.String(), nullable=True))


def downgrade():
    with op.batch_alter_table("financial_statements") as batch_op:
        batch_op.drop_column("audit_opinion")
