"""add thesis_variables_json to stocks

Revision ID: c61ab22a968f
Revises: m3h4i5j6k7l8
Create Date: 2026-06-06 21:20:05.788311

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c61ab22a968f'
down_revision: Union[str, Sequence[str], None] = 'm3h4i5j6k7l8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('stocks', sa.Column('thesis_variables_json', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('stocks', 'thesis_variables_json')
