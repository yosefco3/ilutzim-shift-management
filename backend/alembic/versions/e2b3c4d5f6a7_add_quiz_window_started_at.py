"""add procedures.quiz_window_started_at — quiz availability-window anchor

Adds ``quiz_window_started_at`` (nullable DateTime) to ``procedures``: the
moment the quiz-availability window opened. Reset on EVERY publish path (first
publish, archived→publish, rebroadcast), unlike ``published_at`` which only the
first/archived publish sets. A guard may start the quiz while
now <= anchor + ``procedure_quiz_window_days`` (system setting, 0 = unlimited).

Backfills existing published procedures from ``published_at`` so a window
turned on later measures from the real publish moment, not from NULL.

Ships dark: the new setting defaults to 0 (unlimited), so behavior is unchanged
until the admin sets a window.

Revision ID: e2b3c4d5f6a7
Revises: d0b2c3d4e5f6
Create Date: 2026-07-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e2b3c4d5f6a7'
down_revision: Union[str, Sequence[str], None] = 'd0b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'procedures',
        sa.Column('quiz_window_started_at', sa.DateTime(), nullable=True),
    )
    op.execute(
        "UPDATE procedures SET quiz_window_started_at = published_at "
        "WHERE published_at IS NOT NULL"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('procedures', 'quiz_window_started_at')
