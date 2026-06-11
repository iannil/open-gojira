"""Autopilot P2: plan_templates + seed two built-in templates.

Revision ID: k1f2g3h4i5j6
Revises: j0e1f2g3h4i5
Create Date: 2026-06-06
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "k1f2g3h4i5j6"
down_revision: Union[str, Sequence[str], None] = "j0e1f2g3h4i5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


BUILTIN_TEMPLATES = [
    {
        "name": "高股息蓝筹",
        "description": "原文体系的基准模板：低 PE 分位入场，30% 止盈减半、80% 分位清仓；股息率显著下滑触发减仓；OCF/NI 三年累计 < 0.7 即证伪。",
        "spec_core": {
            "buy_ladder": [
                {"trigger": {"kind": "dyr_ge", "value": 0.055}, "add_pct": 0.05},
                {
                    "trigger": {"kind": "drawdown_from_last_buy", "value": 0.10},
                    "add_pct": 0.05,
                },
                {"trigger": {"kind": "pe_pct_le", "value": 0.10}, "add_pct": 0.05},
            ],
            "sell_ladder": [
                {
                    "trigger": {"kind": "profit_pct_ge", "value": 0.30},
                    "reduce_pct_of_position": 0.5,
                },
                {
                    "trigger": {"kind": "dyr_le", "value": 0.03},
                    "reduce_pct_of_position": 0.5,
                },
                {
                    "trigger": {"kind": "pe_pct_ge", "value": 0.80},
                    "reduce_pct_of_position": 1.0,
                },
            ],
            "invalidation": [
                {"kind": "ocf_to_ni_3y_lt", "value": 0.7},
                {"kind": "dividend_cut_pct_ge", "value": 0.30},
                {"kind": "thesis_manual_revoke", "value": 0},
            ],
            "cooldown_days": 5,
        },
    },
    {
        "name": "资源股周期",
        "description": "周期型资源股专用：更深的 PE 分位入场（15%），50% 止盈减半、85% 分位清仓；冷却 10 天避免周期反复触发。",
        "spec_core": {
            "buy_ladder": [
                {"trigger": {"kind": "pe_pct_le", "value": 0.15}, "add_pct": 0.05},
                {
                    "trigger": {"kind": "drawdown_from_last_buy", "value": 0.15},
                    "add_pct": 0.05,
                },
            ],
            "sell_ladder": [
                {
                    "trigger": {"kind": "profit_pct_ge", "value": 0.50},
                    "reduce_pct_of_position": 0.5,
                },
                {
                    "trigger": {"kind": "pe_pct_ge", "value": 0.85},
                    "reduce_pct_of_position": 1.0,
                },
            ],
            "invalidation": [
                {"kind": "ocf_to_ni_3y_lt", "value": 0.5},
                {"kind": "thesis_manual_revoke", "value": 0},
            ],
            "cooldown_days": 10,
        },
    },
]


def _has_table(bind, name: str) -> bool:
    return name in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "plan_templates"):
        op.create_table(
            "plan_templates",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("name", sa.String, nullable=False),
            sa.Column("description", sa.Text, nullable=False, server_default=""),
            sa.Column("spec_core_json", sa.Text, nullable=False),
            sa.Column(
                "is_builtin",
                sa.Boolean,
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime, nullable=True),
            sa.UniqueConstraint("name", name="uq_plan_templates_name"),
        )
        op.create_index(
            "ix_plan_templates_is_builtin", "plan_templates", ["is_builtin"]
        )

    # Seed built-ins (idempotent — skip if already present by name)
    tbl = sa.table(
        "plan_templates",
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("spec_core_json", sa.Text),
        sa.column("is_builtin", sa.Boolean),
    )
    existing = {
        r[0]
        for r in bind.execute(sa.text("SELECT name FROM plan_templates")).fetchall()
    }
    rows_to_insert = []
    for t in BUILTIN_TEMPLATES:
        if t["name"] in existing:
            continue
        rows_to_insert.append(
            {
                "name": t["name"],
                "description": t["description"],
                "spec_core_json": json.dumps(t["spec_core"], ensure_ascii=False),
                "is_builtin": True,
            }
        )
    if rows_to_insert:
        op.bulk_insert(tbl, rows_to_insert)


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "plan_templates"):
        op.drop_table("plan_templates")
