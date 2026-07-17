"""add procedures.is_default — exactly one default procedure (הנוהל הנוכחי)

Adds ``is_default`` to ``procedures`` (NOT NULL, defaults false) plus a partial
unique index ``WHERE is_default`` so at most ONE procedure may be the default at
a time. Mirrors ``uq_quiz_attempt_one_in_progress`` (emitted for both PostgreSQL
prod and SQLite tests).

NB: the boolean default is the PG literal ``false`` (via ``sa.text('false')``),
NOT an integer like ``'1'``/``'0'`` — PostgreSQL rejects an integer default on a
boolean column (SQLite accepts both, which is why tests wouldn't catch it).

Revision ID: a6c8e0f2b4d6
Revises: f4a1c3e5b7d9
Create Date: 2026-07-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a6c8e0f2b4d6'
down_revision: Union[str, Sequence[str], None] = 'f4a1c3e5b7d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'procedures',
        sa.Column(
            'is_default',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('false'),
        ),
    )
    # Partial unique index: at most one procedure with is_default=true (the
    # current/default procedure). Emitted for both dialects so it holds in
    # SQLite tests and PostgreSQL prod.
    op.create_index(
        'uq_procedure_single_default',
        'procedures',
        ['is_default'],
        unique=True,
        postgresql_where=sa.text('is_default'),
        sqlite_where=sa.text('is_default'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_procedure_single_default', table_name='procedures')
    op.drop_column('procedures', 'is_default')
