"""add schedule_weeks.opened_at

Tracks the first time a week entered OPEN. NULL = never opened, which lets the
auto-open cron skip a week whose submission window already ran and was returned
to CLOSED (so it is never auto-reopened).

Backfill: weeks currently open/locked/published were opened at some point →
set opened_at = updated_at. CLOSED weeks stay NULL (treated as never opened).

Revision ID: b1f3c2a4d5e6
Revises: 95be7724eba5
Create Date: 2026-06-20 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b1f3c2a4d5e6'
down_revision: Union[str, Sequence[str], None] = '95be7724eba5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'schedule_weeks',
        sa.Column('opened_at', sa.DateTime(), nullable=True),
    )
    # Backfill: any week that is not still CLOSED must have been opened before,
    # so stamp opened_at from updated_at. Leave CLOSED weeks NULL.
    # NB: the week_status enum persists the member NAME (uppercase), e.g. 'CLOSED'.
    op.execute(
        "UPDATE schedule_weeks "
        "SET opened_at = updated_at "
        "WHERE status <> 'CLOSED' AND opened_at IS NULL"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('schedule_weeks', 'opened_at')
