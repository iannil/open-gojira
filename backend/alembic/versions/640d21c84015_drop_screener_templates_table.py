"""drop screener_templates table

Revision ID: 640d21c84015
Revises: k1f2g3h4i5j6
Create Date: 2026-06-06 20:08:16.596398

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '640d21c84015'
down_revision: Union[str, Sequence[str], None] = 'k1f2g3h4i5j6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Check if table exists before dropping (for idempotency)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if inspector.has_table('screener_templates'):
        op.drop_table('screener_templates')


def downgrade() -> None:
    """Downgrade schema."""
    op.create_table(
        'screener_templates',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('conditions', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
