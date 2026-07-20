"""add activation_profiles.is_base — permanent base-template marker

Adds ``is_base`` (Boolean, NOT NULL, default ``0``) to ``activation_profiles``.
Unlike the reassignable ``is_default`` board-fallback flag, ``is_base`` is a
PERMANENT mark on the seeded "שגרה" template — the profile every other one is
duplicated from. A base profile can never be deleted.

Backfill: mark the ONE existing base as the profile with the lowest
``display_order`` (ties broken by ``created_at`` then ``id``) — the seeded שגרה
is created first with ``display_order=0``; duplicates always get a higher order.
This picks the original base even in DBs where ``is_default`` has since been
moved to a copy. Fresh installs get ``is_base`` set directly by the seed.

``server_default '0'`` backfills existing rows as non-base first, then the data
step flips exactly one — safe for Railway's auto ``alembic upgrade head``.

Revision ID: a1c2e3f40506
Revises: f8d0a2b4c6e8
Create Date: 2026-07-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1c2e3f40506'
down_revision: Union[str, Sequence[str], None] = 'f8d0a2b4c6e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'activation_profiles',
        sa.Column(
            'is_base',
            sa.Boolean(),
            server_default='0',
            nullable=False,
        ),
    )
    # Backfill: the base is the lowest-display_order profile (the seeded שגרה).
    # Portable across Postgres (prod) and SQLite (tests): pick the id via a
    # subquery ordered by (display_order, created_at, id), then flip that row.
    bind = op.get_bind()
    base_id = bind.execute(
        sa.text(
            "SELECT id FROM activation_profiles "
            "ORDER BY display_order ASC, created_at ASC, id ASC LIMIT 1"
        )
    ).scalar()
    if base_id is not None:
        # Bind a Python bool so the driver adapts it (Postgres `true`, SQLite 1).
        bind.execute(
            sa.text("UPDATE activation_profiles SET is_base = :v WHERE id = :id"),
            {"v": True, "id": base_id},
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('activation_profiles', 'is_base')
