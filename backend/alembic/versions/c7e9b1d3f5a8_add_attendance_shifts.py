"""add attendance_shifts (stage 3 — paired actual shifts)

Derived table built by the pairing engine from attendance_events: an IN punch
opens a shift, the matching OUT closes it. Recomputing a window deletes and
rebuilds its rows. work_date = the check-in's calendar day (night shifts
crossing midnight belong to the day they started).

Revision ID: c7e9b1d3f5a8
Revises: b5d7f9a1c3e6
Create Date: 2026-07-04 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c7e9b1d3f5a8'
down_revision: Union[str, Sequence[str], None] = 'b5d7f9a1c3e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'attendance_shifts',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('work_date', sa.Date(), nullable=False),
        sa.Column('check_in_at', sa.DateTime(), nullable=False),
        sa.Column('check_out_at', sa.DateTime(), nullable=True),
        sa.Column('in_event_id', sa.Uuid(), nullable=False),
        sa.Column('out_event_id', sa.Uuid(), nullable=True),
        sa.Column(
            'status',
            sa.Enum('COMPLETE', 'OPEN', 'MISSING_OUT', name='shift_pair_status'),
            nullable=False,
        ),
        sa.Column('recomputed_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['in_event_id'], ['attendance_events.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['out_event_id'], ['attendance_events.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_attendance_shifts_user_work_date',
        'attendance_shifts',
        ['user_id', 'work_date'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_attendance_shifts_user_work_date', table_name='attendance_shifts')
    op.drop_table('attendance_shifts')
    sa.Enum(name='shift_pair_status').drop(op.get_bind(), checkfirst=True)
