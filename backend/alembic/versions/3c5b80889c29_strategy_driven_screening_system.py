"""strategy_driven_screening_system

Revision ID: 3c5b80889c29
Revises: n4o5p6q7r8s9
Create Date: 2026-06-07 23:41:00.772205

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3c5b80889c29'
down_revision: Union[str, Sequence[str], None] = 'n4o5p6q7r8s9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, table_name: str) -> bool:
    result = bind.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"),
        {"n": table_name},
    )
    return result.fetchone() is not None


def _has_column(bind, table_name: str, column_name: str) -> bool:
    result = bind.execute(
        sa.text(f"PRAGMA table_info({table_name})"),
    )
    return any(row[1] == column_name for row in result.fetchall())


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()

    # 1. Create strategies table if not exists
    if not _has_table(bind, 'strategies'):
        op.create_table('strategies',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('name', sa.String(), nullable=False),
            sa.Column('slug', sa.String(), nullable=False),
            sa.Column('description', sa.Text(), nullable=False),
            sa.Column('kind', sa.String(), nullable=False),
            sa.Column('rule_json', sa.Text(), nullable=False),
            sa.Column('is_builtin', sa.Boolean(), nullable=False),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('slug'),
        )
        op.create_index(op.f('ix_strategies_is_builtin'), 'strategies', ['is_builtin'], unique=False)

    # 2. Drop old tables (if they still exist)
    for tbl in ['resource_profiles', 'plan_templates', 'portfolio_settings',
                'bank_profiles', 'plan_exec_history']:
        if _has_table(bind, tbl):
            op.drop_table(tbl)

    # 3. Create candidates table if not exists
    if not _has_table(bind, 'candidates'):
        op.create_table('candidates',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('plan_id', sa.Integer(), nullable=False),
            sa.Column('stock_code', sa.String(), nullable=False),
            sa.Column('status', sa.String(), nullable=False),
            sa.Column('first_seen_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
            sa.Column('last_confirmed_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
            sa.Column('removed_at', sa.DateTime(), nullable=True),
            sa.Column('last_eval_json', sa.Text(), nullable=True),
            sa.Column('pinned', sa.Boolean(), nullable=False),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(['plan_id'], ['plans.id']),
            sa.ForeignKeyConstraint(['stock_code'], ['stocks.code']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_candidates_plan_id'), 'candidates', ['plan_id'], unique=False)
        op.create_index(op.f('ix_candidates_status'), 'candidates', ['status'], unique=False)
        op.create_index(op.f('ix_candidates_stock_code'), 'candidates', ['stock_code'], unique=False)

    # 4. Alter drafts table — drop old columns if they exist
    drafts_alter = False
    if _has_column(bind, 'drafts', 'plan_version') or _has_column(bind, 'drafts', 'exec_history_id'):
        with op.batch_alter_table('drafts') as batch_op:
            if _has_column(bind, 'drafts', 'plan_version'):
                batch_op.drop_column('plan_version')
            if _has_column(bind, 'drafts', 'exec_history_id'):
                batch_op.drop_column('exec_history_id')

    # 5. Alter plans table — only if still old schema (has 'code' column)
    if _has_column(bind, 'plans', 'code'):
        with op.batch_alter_table('plans', recreate='always') as batch_op:
            batch_op.add_column(sa.Column('name', sa.String(), nullable=False, server_default=''))
            batch_op.add_column(sa.Column('slug', sa.String(), nullable=False, server_default=''))
            batch_op.add_column(sa.Column('description', sa.Text(), nullable=False, server_default=''))
            batch_op.add_column(sa.Column('strategy_composition_json', sa.Text(), nullable=False, server_default='{}'))
            batch_op.add_column(sa.Column('scan_scope_json', sa.Text(), nullable=False, server_default='{}'))
            batch_op.add_column(sa.Column('schedule_cron', sa.String(), nullable=False, server_default=''))
            batch_op.add_column(sa.Column('trading_rules_json', sa.Text(), nullable=True))
            batch_op.add_column(sa.Column('last_run_at', sa.DateTime(), nullable=True))
            batch_op.add_column(sa.Column('last_run_summary', sa.Text(), nullable=True))
            batch_op.add_column(sa.Column('is_builtin', sa.Boolean(), nullable=False, server_default=sa.text('0')))
            batch_op.drop_column('effective_until')
            batch_op.drop_column('thesis')
            batch_op.drop_column('spec_json')
            batch_op.drop_column('version')
            if _has_column(bind, 'plans', 'theme_id'):
                batch_op.drop_column('theme_id')
            batch_op.drop_column('code')
            batch_op.drop_column('effective_from')
            batch_op.create_unique_constraint('uq_plans_slug', ['slug'])
            batch_op.create_index(batch_op.f('ix_plans_is_builtin'), ['is_builtin'], unique=False)

    # 6. Alter watchlist_items — add source_candidate_id if not exists
    if not _has_column(bind, 'watchlist_items', 'source_candidate_id'):
        with op.batch_alter_table('watchlist_items') as batch_op:
            batch_op.add_column(sa.Column('source_candidate_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                'fk_watchlist_items_source_candidate_id',
                'candidates', ['source_candidate_id'], ['id'],
            )
    # Drop old columns if they exist
    if _has_column(bind, 'watchlist_items', 'target_pe_pct'):
        with op.batch_alter_table('watchlist_items') as batch_op:
            batch_op.drop_column('target_pe_pct')
    if _has_column(bind, 'watchlist_items', 'target_pb_pct'):
        with op.batch_alter_table('watchlist_items') as batch_op:
            batch_op.drop_column('target_pb_pct')


def downgrade() -> None:
    """Downgrade schema — not supported for this major refactor."""
    raise NotImplementedError("Downgrade not supported for strategy_driven_screening_system migration")
