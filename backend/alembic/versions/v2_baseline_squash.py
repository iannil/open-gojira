"""v2 squashed baseline — full schema from current models

Revision ID: v2_baseline_squash
Revises:
Create Date: 2026-06-25

Background:
  The original base migration (3c5b80889c29) that created `stocks` + the core
  Lixinger tables was deleted in an earlier cleanup, leaving the 34-migration
  chain rootless — `alembic upgrade head` from an empty DB failed ("no such
  table: stocks"), so a clean-slate 全量发布 was impossible.

  Per 2026-06-25 decision (trading-philosophy.md work): squash the broken
  incremental history into ONE baseline that builds the full current schema
  directly from the SQLAlchemy models (Base.metadata). The cumulative effect of
  the old 34 migrations == the current models, so this is equivalent for a
  fresh deploy and guarantees the migration schema matches the code.

  EXISTING databases already at the old head must be stamped once (no re-run):
      alembic stamp v2_baseline_squash
"""
from alembic import op

from app.db.base import Base
import app.models  # noqa: F401  — register every model on Base.metadata


# revision identifiers, used by Alembic.
revision = "v2_baseline_squash"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the entire current schema from the models."""
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
