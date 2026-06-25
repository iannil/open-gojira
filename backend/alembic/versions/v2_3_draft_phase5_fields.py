"""v2 (2026-06-25): Phase-5 draft_generator fields on drafts

Revision ID: v2_3_draft_phase5_fields
Revises: v2_baseline_squash
Create Date: 2026-06-25

Adds decision 9/10 + §7 fields to drafts (research_report_id / target_price /
strategy_tier / sizing_logic / thesis_status / expires_at / price_ranges_json /
serenity_thesis).

Guarded ADD COLUMN: the v2_baseline_squash baseline builds `drafts` via
create_all from the current model (already includes these columns on a fresh
deploy), so this migration only adds columns that are actually missing — safe
to run on both fresh and existing databases.
"""
from alembic import op
import sqlalchemy as sa


revision = "v2_3_draft_phase5_fields"
down_revision = "v2_baseline_squash"
branch_labels = None
depends_on = None


_NEW_COLUMNS = [
    ("research_report_id", sa.Integer, {"nullable": True}),
    ("target_price", sa.Float, {"nullable": True}),
    ("strategy_tier", sa.String, {"nullable": True}),
    ("sizing_logic", sa.Text, {"nullable": True}),
    ("thesis_status", sa.String, {"nullable": True}),
    ("expires_at", sa.DateTime, {"nullable": True}),
    ("price_ranges_json", sa.JSON, {"nullable": True}),
    ("serenity_thesis", sa.Text, {"nullable": True}),
]


def upgrade() -> None:
    bind = op.get_bind()
    existing = {c["name"] for c in sa.inspect(bind).get_columns("drafts")}
    for name, type_, kw in _NEW_COLUMNS:
        if name not in existing:
            op.add_column("drafts", sa.Column(name, type_(), **kw))
    if "ix_drafts_research_report_id" not in {
        ix["name"] for ix in sa.inspect(bind).get_indexes("drafts")
    }:
        op.create_index("ix_drafts_research_report_id", "drafts", ["research_report_id"])
    if "ix_drafts_expires_at" not in {
        ix["name"] for ix in sa.inspect(bind).get_indexes("drafts")
    }:
        op.create_index("ix_drafts_expires_at", "drafts", ["expires_at"])


def downgrade() -> None:
    for name, _, _ in _NEW_COLUMNS:
        op.drop_column("drafts", name)
