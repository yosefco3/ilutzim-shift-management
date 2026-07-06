"""add positions.event_required_count (fixed participant count for events)

An event position (``is_event``) may carry a FIXED participant count — e.g.
ישיבת מועצה needs 4 guards. NULL keeps the current unlimited behaviour (רענון).
A positive int tiles the event cell into that many participant slots. Adds a
nullable integer column, defaulting NULL so every existing event stays unlimited.

Revision ID: c9e2d4a6f8b1
Revises: b8d1f2a3c4e5
Create Date: 2026-07-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c9e2d4a6f8b1'
down_revision: Union[str, Sequence[str], None] = 'b8d1f2a3c4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "positions",
        sa.Column(
            "event_required_count",
            sa.Integer(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("positions", "event_required_count")
