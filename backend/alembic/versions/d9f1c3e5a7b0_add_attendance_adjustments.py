"""add attendance_adjustments (stage 3 — admin corrections audit trail)

Every manual correction is a row: action (edit_time/add_punch/void_punch/
mark_absence), the superseded/created punch, before/after snapshots and a
required reason. The raw punch log stays immutable; derived shifts are
recomputed from the effective (non-superseded) events.

Revision ID: d9f1c3e5a7b0
Revises: c7e9b1d3f5a8
Create Date: 2026-07-04 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd9f1c3e5a7b0'
down_revision: Union[str, Sequence[str], None] = 'c7e9b1d3f5a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'attendance_adjustments',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('work_date', sa.Date(), nullable=False),
        sa.Column(
            'action',
            sa.Enum(
                'EDIT_TIME', 'ADD_PUNCH', 'VOID_PUNCH', 'MARK_ABSENCE',
                name='adjustment_action',
            ),
            nullable=False,
        ),
        sa.Column('target_event_id', sa.Uuid(), nullable=True),
        sa.Column('before', sa.JSON(), nullable=True),
        sa.Column('after', sa.JSON(), nullable=True),
        sa.Column('reason', sa.String(length=500), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(
            ['target_event_id'], ['attendance_events.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_attendance_adjustments_user_date',
        'attendance_adjustments',
        ['user_id', 'work_date'],
    )
    op.create_index(
        'ix_attendance_adjustments_target',
        'attendance_adjustments',
        ['target_event_id'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_attendance_adjustments_target', table_name='attendance_adjustments')
    op.drop_index('ix_attendance_adjustments_user_date', table_name='attendance_adjustments')
    op.drop_table('attendance_adjustments')
    sa.Enum(name='adjustment_action').drop(op.get_bind(), checkfirst=True)
