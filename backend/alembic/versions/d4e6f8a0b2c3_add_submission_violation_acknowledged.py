"""add weekly_submissions.violation_acknowledged

Lets an admin acknowledge a guard's rule violations so the submissions UI can
hide the violation marker (an orange dot) for that row. Existing rows default to
false (not yet acknowledged).

Revision ID: d4e6f8a0b2c3
Revises: c2d4e6f8a0b1
Create Date: 2026-06-20 19:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd4e6f8a0b2c3'
down_revision: Union[str, Sequence[str], None] = 'c2d4e6f8a0b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'weekly_submissions',
        sa.Column(
            'violation_acknowledged',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('weekly_submissions', 'violation_acknowledged')
