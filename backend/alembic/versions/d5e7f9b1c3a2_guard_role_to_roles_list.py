"""convert single guard role enum to a multi-value roles list

Replaces the single ``users.role`` enum column with a ``users.roles`` JSONB
list so a guard can hold several attributes at once (חמוש / לא חמוש / אחמ"ש /
רכב סיור). The old role values are dropped — data loss here is intentional and
approved.

Revision ID: d5e7f9b1c3a2
Revises: 997d74570060
Create Date: 2026-06-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd5e7f9b1c3a2'
down_revision: Union[str, Sequence[str], None] = '997d74570060'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'users',
        sa.Column(
            'roles',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default='[]',
        ),
    )
    op.drop_column('users', 'role')
    # The old native enum type is now unreferenced — drop it.
    op.execute('DROP TYPE IF EXISTS user_role')


def downgrade() -> None:
    """Downgrade schema (best effort — role values are not recoverable)."""
    user_role = postgresql.ENUM(
        'AHMASH', 'BASIC_GUARD', 'LEVEL_B', 'NINE_HOURS', 'UNARMED', 'CHECKER',
        name='user_role',
    )
    user_role.create(op.get_bind(), checkfirst=True)
    op.add_column(
        'users',
        sa.Column(
            'role',
            user_role,
            nullable=False,
            server_default='AHMASH',
        ),
    )
    op.drop_column('users', 'roles')
