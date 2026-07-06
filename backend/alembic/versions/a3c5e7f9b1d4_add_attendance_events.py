"""add attendance_events (stage 3 — attendance raw punch log)

The append-only raw punch log for the attendance system: who punched, which
direction (in/out), when, from which source (telegram/manual; device reserved),
and the punch-moment location for Telegram punches. Application code never
updates or deletes rows here — corrections are new `manual` events plus an
audit record, and derived tables are recomputed from this log.

Revision ID: a3c5e7f9b1d4
Revises: e1a3c5b7d9f2
Create Date: 2026-07-04 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a3c5e7f9b1d4'
down_revision: Union[str, Sequence[str], None] = 'e1a3c5b7d9f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'attendance_events',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column(
            'direction',
            sa.Enum('IN', 'OUT', name='punch_direction'),
            nullable=False,
        ),
        sa.Column('punched_at', sa.DateTime(), nullable=False),
        sa.Column(
            'source',
            sa.Enum('TELEGRAM', 'MANUAL', 'DEVICE', name='punch_source'),
            nullable=False,
        ),
        sa.Column('lat', sa.Float(), nullable=True),
        sa.Column('lng', sa.Float(), nullable=True),
        sa.Column('accuracy_m', sa.Float(), nullable=True),
        sa.Column('distance_from_site_m', sa.Float(), nullable=True),
        sa.Column('out_of_radius', sa.Boolean(), nullable=True),
        sa.Column('note', sa.String(length=500), nullable=True),
        sa.Column('created_by_admin', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_attendance_events_user_punched',
        'attendance_events',
        ['user_id', 'punched_at'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_attendance_events_user_punched', table_name='attendance_events')
    op.drop_table('attendance_events')
    sa.Enum(name='punch_direction').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='punch_source').drop(op.get_bind(), checkfirst=True)
