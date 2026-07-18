"""add procedure_read_receipts — first-open receipt per guard per procedure

Records the first time each guard opened a procedure's WebApp reading page, so
the admin results screen can show a "קרא" column alongside pass/fail. Unique
``(procedure_id, user_id)``: re-opens never duplicate or overwrite the original
``first_read_at``. Both FKs cascade (hard-deleting a procedure erases its
receipts; deleting a guard erases theirs).

Ships dark behind PROCEDURES_ENABLED (default False).

Revision ID: d0b2c3d4e5f6
Revises: c0a1e1f2a3b4
Create Date: 2026-07-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd0b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'c0a1e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'procedure_read_receipts',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('procedure_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('first_read_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['procedure_id'], ['procedures.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('procedure_id', 'user_id', name='uq_procedure_read_once'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('procedure_read_receipts')
