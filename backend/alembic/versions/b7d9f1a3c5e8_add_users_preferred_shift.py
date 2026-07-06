"""add users.preferred_shift (optional preferred shift for auto-scheduling)

Optional ShiftType value (morning/afternoon/night) chosen in the guard form.
NULL = no preference. Informational for now — becomes an input to the future
auto-scheduler.

Revision ID: b7d9f1a3c5e8
Revises: f3a5c7e9d1b4
Create Date: 2026-07-04 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b7d9f1a3c5e8'
down_revision: Union[str, Sequence[str], None] = 'f3a5c7e9d1b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'users',
        sa.Column('preferred_shift', sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'preferred_shift')
