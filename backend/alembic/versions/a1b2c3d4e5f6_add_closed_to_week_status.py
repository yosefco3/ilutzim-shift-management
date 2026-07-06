"""add CLOSED value to week_status enum

Revision ID: a1b2c3d4e5f6
Revises: 68d1f37c2543
Create Date: 2026-06-08 10:10:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '68d1f37c2543'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add CLOSED to the week_status enum."""
    op.execute("ALTER TYPE week_status ADD VALUE IF NOT EXISTS 'CLOSED'")


def downgrade() -> None:
    """Cannot easily remove enum values in PostgreSQL — no-op downgrade."""
    # PostgreSQL does not support removing enum values without recreating the type.
    pass