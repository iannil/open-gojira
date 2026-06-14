"""B3 themes expansion: add 民生 / 科技 / 信息 themes

Revision ID: t10_1_b3_themes_expansion
Revises: t9_1_g4_resource_flags
Create Date: 2026-06-14

B3 (invest3 §24): expand Theme table from 4 (能源/资源/金融/粮食) to 7.
- 民生: covers 药店零售 / 旅游景区 (previously orphan patterns with theme_id=null)
- 科技 / 信息: future-proofing (no current pattern uses them; reserved for v3
  when AI / cybersecurity patterns are added)

Source: business pattern progress doc 2026-06-14-business-pattern-module.md
called out the orphan theme_id issue explicitly.
"""
revision = "t10_1_b3_themes_expansion"
down_revision = "t9_1_g4_resource_flags"
branch_labels = None
depends_on = None

from alembic import op  # noqa: E402
import sqlalchemy as sa  # noqa: E402


def upgrade():
    conn = op.get_bind()
    themes_table = sa.table(
        "themes",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("description", sa.String),
        sa.column("target_weight_pct", sa.Float),
    )

    # Check if 民生 already exists (idempotent)
    existing = conn.execute(
        sa.text("SELECT name FROM themes WHERE name IN ('民生', '科技', '信息')")
    ).fetchall()
    existing_names = {r[0] for r in existing}

    rows = []
    if "民生" not in existing_names:
        rows.append({
            "name": "民生",
            "description": "民生主线 - 包括医药零售、消费、旅游等民生相关行业",
            "target_weight_pct": 0.0,
        })
    if "科技" not in existing_names:
        rows.append({
            "name": "科技",
            "description": "科技安全主线 - 包括 AI、芯片、创新药等(预留,v3 启用)",
            "target_weight_pct": 0.0,
        })
    if "信息" not in existing_names:
        rows.append({
            "name": "信息",
            "description": "信息安全主线 - 包括网络安全、数据安全等(预留,v3 启用)",
            "target_weight_pct": 0.0,
        })

    if rows:
        op.bulk_insert(themes_table, rows)


def downgrade():
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM themes WHERE name IN ('民生', '科技', '信息')")
    )
