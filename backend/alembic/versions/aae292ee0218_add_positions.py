"""add positions

Revision ID: aae292ee0218
Revises: 6abbd8e22af6
Create Date: 2026-06-16 20:33:58.266293

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'aae292ee0218'
down_revision: Union[str, Sequence[str], None] = '6abbd8e22af6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # NOTE: ``shift_type`` enum already exists (created by part-A shift_window);
    # reference it with create_type=False so we don't try to recreate it.
    shift_type = postgresql.ENUM(
        'MORNING', 'AFTERNOON', 'NIGHT', name='shift_type', create_type=False,
    )
    op.create_table('positions',
    sa.Column('profile_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('shift', shift_type, nullable=False),
    sa.Column('day_schedules', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('required_attributes', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('display_order', sa.Integer(), server_default='0', nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['profile_id'], ['activation_profiles.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_positions_profile_id'), 'positions', ['profile_id'], unique=False)
    # NOTE: autogenerate also flagged op.drop_table('schedule_events') — that is a
    # pre-existing DB drift (legacy table with no model), out of scope. Removed.


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_positions_profile_id'), table_name='positions')
    op.drop_table('positions')
