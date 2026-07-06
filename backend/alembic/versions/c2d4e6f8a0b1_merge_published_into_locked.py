"""merge PUBLISHED week status into LOCKED (3-state model)

The week lifecycle drops PUBLISHED: the admin "publish" action now finalizes a
week to LOCKED. Migrate any existing PUBLISHED rows to LOCKED so they load under
the new enum (SQLAlchemy maps the stored name to a Python member).

The Postgres enum TYPE 'week_status' keeps its 'PUBLISHED' value (now unused) —
removing a value from a PG enum requires recreating the type, which is not worth
it; no row references it after this migration.

Revision ID: c2d4e6f8a0b1
Revises: b1f3c2a4d5e6
Create Date: 2026-06-20 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c2d4e6f8a0b1'
down_revision: Union[str, Sequence[str], None] = 'b1f3c2a4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # status persists the enum member NAME (uppercase).
    op.execute("UPDATE schedule_weeks SET status = 'LOCKED' WHERE status = 'PUBLISHED'")


def downgrade() -> None:
    """Downgrade schema.

    Irreversible data merge — PUBLISHED and LOCKED are indistinguishable after
    upgrade, so downgrade is a no-op (the 'PUBLISHED' enum value still exists).
    """
    pass
