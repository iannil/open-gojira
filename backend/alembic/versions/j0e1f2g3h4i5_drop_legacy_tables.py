"""Autopilot Step 4 cleanup: drop legacy analysis/discipline/profile tables.

Revision ID: j0e1f2g3h4i5
Revises: i9d0e1f2g3h4
Create Date: 2026-06-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "j0e1f2g3h4i5"
down_revision: Union[str, Sequence[str], None] = "i9d0e1f2g3h4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tables the autopilot redesign no longer needs. `audit_logs` now replaces
# `action_logs`; the rest backed analyst-only features deleted in Step 4.
_LEGACY_TABLES = (
    "action_logs",
    "analysis_snapshots",
    "bank_profiles",
    "candidate_pools",
    "discipline_checks",
    "resource_profiles",
)


def _has_table(bind, name: str) -> bool:
    return name in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    for name in _LEGACY_TABLES:
        if _has_table(bind, name):
            op.drop_table(name)


def downgrade() -> None:
    # Down-migration not supported — legacy tables are gone for good.
    # If a rollback is needed, restore the pre-revision schema from a backup
    # or run `Base.metadata.create_all` against an earlier branch.
    pass
