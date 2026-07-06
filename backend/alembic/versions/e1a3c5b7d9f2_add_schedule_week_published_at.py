"""add schedule_weeks.published_at

Tracks the last time a week's schedule was broadcast via the "publish" action.
NULL = never published. Publish now keeps the week CLOSED (it no longer locks),
so the status can no longer encode "already published" — this timestamp does.
The admin UI uses it to show "publish" vs "re-publish".

No backfill: any week that was previously LOCKED via the old publish path is
left NULL. The distinction only matters going forward for the upcoming week the
admin is building; historical weeks are read-only regardless.

Revision ID: e1a3c5b7d9f2
Revises: d3f7a1b9c2e4
Create Date: 2026-07-04 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e1a3c5b7d9f2'
down_revision: Union[str, Sequence[str], None] = 'd3f7a1b9c2e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'schedule_weeks',
        sa.Column('published_at', sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('schedule_weeks', 'published_at')
