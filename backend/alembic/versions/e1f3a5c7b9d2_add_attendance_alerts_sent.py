"""add attendance_alerts_sent (stage 3 — admin alert idempotency ledger)

One row per dispatched admin alert (no_show / long_shift / short_rest), with a
unique (alert_type, user_id, ref_key) so the 10-minute scheduler check alerts
each incident exactly once.

Revision ID: e1f3a5c7b9d2
Revises: d9f1c3e5a7b0
Create Date: 2026-07-04 23:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e1f3a5c7b9d2'
down_revision: Union[str, Sequence[str], None] = 'd9f1c3e5a7b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'attendance_alerts_sent',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('alert_type', sa.String(length=20), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('ref_date', sa.Date(), nullable=False),
        sa.Column('ref_key', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('alert_type', 'user_id', 'ref_key', name='uq_attendance_alert_once'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('attendance_alerts_sent')
