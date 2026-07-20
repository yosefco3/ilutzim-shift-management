"""add activation_profiles.day_labels — per-day free-text label map

Adds ``day_labels`` (JSONB, NOT NULL, default ``{}``) to ``activation_profiles``:
a per-day free-text label map keyed by day index "0".."6" (0=ראשון … 6=שבת),
e.g. ``{"4": "ט׳ באב"}``. Shown later in the matrix editor and board headers to
annotate a day for the whole profile (a holiday, an event, etc.).

``server_default '{}'`` backfills existing rows with an empty map so old profiles
read as "no labels" — safe for Railway's auto ``alembic upgrade head`` on deploy.

Ships dark: nothing user-visible yet. The labels are read/rendered only in a
later step, after the whole editor works (deploy-safe sequencing).

Revision ID: f8d0a2b4c6e8
Revises: e2b3c4d5f6a7
Create Date: 2026-07-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f8d0a2b4c6e8'
down_revision: Union[str, Sequence[str], None] = 'e2b3c4d5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'activation_profiles',
        sa.Column(
            'day_labels',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default='{}',
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('activation_profiles', 'day_labels')
