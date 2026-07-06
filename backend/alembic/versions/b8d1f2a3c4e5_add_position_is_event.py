"""add positions.is_event (event / non-splitting position)

An *event* position (רענון, ישיבת מועצה) hosts several guards on the same window
simultaneously — the cell is never split between them. Adds a boolean flag,
defaulting False so every existing position stays a normal (splitting) position.

Revision ID: b8d1f2a3c4e5
Revises: e7a1c3f5b9d2
Create Date: 2026-07-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b8d1f2a3c4e5'
down_revision: Union[str, Sequence[str], None] = 'e7a1c3f5b9d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "positions",
        sa.Column(
            "is_event",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("positions", "is_event")
