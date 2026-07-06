"""split_full_name_to_first_last

Revision ID: 68d1f37c2543
Revises: e070f2f048c6
Create Date: 2026-06-06 08:07:39.430671

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '68d1f37c2543'
down_revision: Union[str, Sequence[str], None] = 'e070f2f048c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Step 1: Add new columns as nullable
    op.add_column('users', sa.Column('first_name', sa.String(length=50), nullable=True))
    op.add_column('users', sa.Column('last_name', sa.String(length=50), nullable=True))

    # Step 2: Migrate existing data - split full_name on first space
    users = sa.table('users', sa.column('first_name', sa.String),
                     sa.column('last_name', sa.String),
                     sa.column('full_name', sa.String))
    op.execute(
        "UPDATE users SET "
        "first_name = split_part(full_name, ' ', 1), "
        "last_name = CASE "
        "  WHEN position(' ' in full_name) > 0 "
        "  THEN substring(full_name from position(' ' in full_name) + 1) "
        "  ELSE full_name "
        "END "
        "WHERE full_name IS NOT NULL"
    )

    # Step 3: Make columns NOT NULL
    op.alter_column('users', 'first_name', nullable=False)
    op.alter_column('users', 'last_name', nullable=False)

    # Step 4: Drop old column
    op.drop_column('users', 'full_name')


def downgrade() -> None:
    """Downgrade schema."""
    # Step 1: Add full_name back
    op.add_column('users', sa.Column('full_name', sa.VARCHAR(length=100), autoincrement=False, nullable=True))

    # Step 2: Merge first_name + last_name into full_name
    op.execute(
        "UPDATE users SET full_name = first_name || ' ' || last_name "
        "WHERE first_name IS NOT NULL AND last_name IS NOT NULL"
    )

    # Step 3: Make NOT NULL
    op.alter_column('users', 'full_name', nullable=False)

    # Step 4: Drop new columns
    op.drop_column('users', 'last_name')
    op.drop_column('users', 'first_name')